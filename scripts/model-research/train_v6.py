"""Chronological comparison, separate place/pair models, calibration and selective prediction.

The former v5 holdout is explicitly a reused audit, never a new untouched test.
Do not tune model or policy after inspecting confirmation/audit results.
"""
import argparse
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime,timedelta
from pathlib import Path
import numpy as np
from scipy.special import expit,logit
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from features_v6 import FEATURES,VERSION,prepare,validate_rows
from train import prepare as legacy_prepare, probabilities as legacy_probabilities

SEED=20260912
PAIR_COLUMNS=list(range(20))+list(range(27,32))
CONFIGS=[{'name':'linear_all','kind':'linear','years':0,'half_life':0},
 {'name':'tree_1y','kind':'tree','years':1,'half_life':0},
 {'name':'tree_3y','kind':'tree','years':3,'half_life':0},
 {'name':'tree_all','kind':'tree','years':0,'half_life':0},
 {'name':'tree_recent','kind':'tree','years':0,'half_life':365}]
FOLDS=[('20240701','20250101'),('20250101','20250701'),('20250701','20260101')]

def pair_features(X):
 n=len(X);pairs=np.array([(i,j) for i in range(n) for j in range(i+1,n)])
 a=X[pairs[:,0]][:,PAIR_COLUMNS];b=X[pairs[:,1]][:,PAIR_COLUMNS]
 return np.column_stack(((a+b)/2,np.minimum(a,b),np.abs(a-b),X[pairs[:,0],20:27])),pairs

def package(rows,kind):
 xx=[];yy=[];ww=[];segments=[];offset=0
 for r in rows:
  X=np.asarray(r['X']);truth=set(r['order'][:r['place_k'] if kind=='place' else 3])
  if kind=='place':Y=np.array([i in truth for i in range(len(X))],int);numbers=[[x] for x in r['numbers']]
  else:
   X,ij=pair_features(X);Y=np.array([i in truth and j in truth for i,j in ij],int);numbers=[[r['numbers'][i],r['numbers'][j]] for i,j in ij]
  segments.append({'race':r,'lo':offset,'hi':offset+len(X),'numbers':numbers});offset+=len(X)
  xx.append(X);yy.append(Y);ww.extend([1/len(X)]*len(X))
 return np.concatenate(xx),np.concatenate(yy),np.asarray(ww),segments

def fit(rows,kind,config,cutoff):
 end=datetime.strptime(cutoff,'%Y%m%d');lower=(end-timedelta(days=365*config['years'])).strftime('%Y%m%d') if config['years'] else '20220101'
 use=[r for r in rows if max(lower,'20220101')<=r['date']<cutoff]
 if len(use)<500:raise ValueError('Insufficient training races')
 X,y,w,segments=package(use,kind)
 if config['half_life']:
  for s in segments:
   days=(end-datetime.strptime(s['race']['date'],'%Y%m%d')).days
   w[s['lo']:s['hi']]*=2**(-days/config['half_life'])
 w*=len(w)/w.sum()
 if config['kind']=='linear':m=LogisticRegression(C=.1,max_iter=300,random_state=SEED)
 else:m=HistGradientBoostingClassifier(max_iter=90,max_leaf_nodes=7,learning_rate=.07,min_samples_leaf=80,l2_regularization=10,early_stopping=False,random_state=SEED)
 m.fit(X,y,sample_weight=w)
 return m,len(use)

def export_model(m):
 if isinstance(m,LogisticRegression):return {'kind':'linear','bias':float(m.intercept_[0]),'weights':m.coef_[0].tolist()}
 trees=[]
 for iteration in m._predictors:
  nodes=[]
  for node in iteration[0].nodes:
   if node['is_categorical']:raise ValueError('Only numerical trees supported')
   nodes.append([int(node['is_leaf']),int(node['feature_idx']),float(node['num_threshold']),int(node['left']),int(node['right']),float(node['value'])])
  trees.append(nodes)
 return {'kind':'tree','bias':float(m._baseline_prediction[0,0]),'trees':trees}

def predict_export(model,X):
 X=np.asarray(X)
 if model['kind']=='linear':z=X@np.array(model['weights'])+model['bias']
 else:
  z=np.full(len(X),model['bias'])
  for tree in model['trees']:
   for i,x in enumerate(X):
    n=0
    while not tree[n][0]:
     row=tree[n];n=row[3] if x[row[1]]<=row[2] else row[4]
    z[i]+=tree[n][5]
 return expit(z)

def calibration(model,rows,kind):
 X,y,w,_=package(rows,kind);raw=model.predict_proba(X)[:,1];z=logit(np.clip(raw,1e-6,1-1e-6)).reshape(-1,1)
 m=LogisticRegression(C=100,max_iter=200).fit(z,y,sample_weight=w*len(w)/w.sum())
 # A positive mapping preserves ranking; never invert a weak model using the calibration labels.
 return {'a':max(.01,float(m.coef_[0,0])),'b':float(m.intercept_[0])}

def predictions(model,rows,kind,cal=None):
 X,y,w,segments=package(rows,kind);p=model.predict_proba(X)[:,1]
 if cal:p=expit(cal['a']*logit(np.clip(p,1e-6,1-1e-6))+cal['b'])
 out=[]
 for s in segments:
  r=s['race'];pp=p[s['lo']:s['hi']];ys=y[s['lo']:s['hi']];order=np.argsort(-pp,kind='stable');i=int(order[0]);nums=s['numbers'][i]
  qualities=[r['quality'][r['numbers'].index(n)] for n in nums]
  out.append({'date':r['date'],'venue':r['venue'],'race_no':r['race_no'],'numbers':nums,'prob':float(pp[i]),
   'gap':float(pp[i]-pp[order[1]]),'hit':int(ys[i]),'brier':float(np.mean((pp-ys)**2)),
   'starts':min(x['starts'] for x in qualities),'sparse':max(x['sparse'] for x in qualities),
   'field_size':len(r['numbers'])})
 return out

def wilson(h,n):
 if not n:return [0.,1.]
 p=h/n;z=1.96;den=1+z*z/n;mid=(p+z*z/(2*n))/den;rad=z*np.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
 return [float(mid-rad),float(mid+rad)]

def summary(items):
 n=len(items);h=sum(x['hit'] for x in items)
 return {'races':n,'hits':h,'hit_rate':h/n if n else None,'hit_rate_95ci':wilson(h,n),
  'brier':float(np.mean([x['brier'] for x in items])) if n else None,
  'top_brier':float(np.mean([(x['prob']-x['hit'])**2 for x in items])) if n else None}

def reliability(items):
 bins=[]
 for lo in [0,.2,.4,.6,.8]:
  a=[x for x in items if lo<=x['prob']<lo+.2+ (1e-10 if lo==.8 else 0)]
  bins.append({'from':lo,'to':lo+.2,'races':len(a),'predicted':float(np.mean([x['prob'] for x in a])) if a else None,'actual':summary(a)['hit_rate']})
 return bins

def incumbent_predictions(rows,weights,kind):
 out=[]
 for r in rows:
  p,q=legacy_probabilities(r['X']@weights,r['place_k']);n=len(p)
  numbers=[h['number'] for h in r['form']]
  if kind=='place':
   truth=set(r['order'][:r['place_k']]);i=int(np.argmax(p));nums=[numbers[i]];prob=p[i];hit=int(i in truth)
   brier=float(np.mean([(p[j]-int(j in truth))**2 for j in range(n)]))
  else:
   a,b=np.unravel_index(np.argmax(q),q.shape);nums=[numbers[a],numbers[b]];prob=q[a,b];hit=int(a in set(r['order'][:3]) and b in set(r['order'][:3]))
   truth=set(r['order'][:3]);brier=float(np.mean([(q[i,j]-int(i in truth and j in truth))**2 for i in range(n) for j in range(i+1,n)]))
  out.append({'date':r['date'],'venue':r['venue'],'race_no':r['race_no'],'numbers':nums,'prob':float(prob),'hit':hit,'brier':brier})
 return out

def paired_ci(old,new):
 a={(x['date'],x['venue'],x['race_no']):x for x in old};days=defaultdict(list)
 for x in new:
  key=(x['date'],x['venue'],x['race_no'])
  if key in a:days[x['date']].append(x['hit']-a[key]['hit'])
 keys=sorted(days);rng=np.random.default_rng(SEED);values=[]
 for _ in range(1200):
  sample=rng.choice(keys,len(keys));values.append(np.mean([v for d in sample for v in days[d]]))
 return np.quantile(values,[.025,.975]).tolist()

def matches(x,p):return x['venue'] in p.get('venues',['seoul','busan','jeju']) and x['prob']>=p['min_probability'] and x['gap']>=p['min_gap'] and x['starts']>=p['min_starts'] and x['sparse']<=p['max_sparse']

def uplift_ci(allitems,selected,seed=SEED):
 # Date-cluster bootstrap of selective minus all-race hit rate, preserving meeting dependence.
 days=sorted({x['date'] for x in allitems});rng=np.random.default_rng(seed)
 def totals(items):
  d=defaultdict(lambda:[0,0])
  for x in items:d[x['date']][0]+=x['hit'];d[x['date']][1]+=1
  return np.array([d[k] for k in days],float)
 a,b=totals(allitems),totals(selected);values=[]
 for _ in range(1200):
  ix=rng.integers(0,len(days),len(days));sa=a[ix].sum(axis=0);sb=b[ix].sum(axis=0)
  if sb[1]:values.append(sb[0]/sb[1]-sa[0]/sa[1])
 return np.quantile(values,[.025,.975]).tolist() if values else [-1,1]

def choose_policy(items):
 possibilities=[]
 for threshold in [.35,.45,.55,.65,.75]:
  for gap in [0,.04]:
   for starts,sparse in [(0,1),(3,.3)]:
    p={'min_probability':threshold,'min_gap':gap,'min_starts':starts,'max_sparse':sparse}
    a=[x for x in items if matches(x,p)];s=summary(a)
    if len(a)>=80 and .15<=len(a)/len(items)<=.65:
     possibilities.append((s['hit_rate_95ci'][0],len(a),p))
 if not possibilities:return None
 policy=max(possibilities,key=lambda x:(x[0],x[1]))[2]
 # Venue eligibility is frozen on policy-selection dates, never chosen using confirmation labels.
 chosen=[x for x in items if matches(x,policy)]
 policy['venues']=[v for v in ['seoul','busan','jeju'] if len([x for x in chosen if x['venue']==v])>=20 and summary([x for x in chosen if x['venue']==v])['hit_rate']>summary([x for x in items if x['venue']==v])['hit_rate']]
 return policy

def validate_policy(policy,items):
 a=[x for x in items if policy and matches(x,policy)];s=summary(a);ci=uplift_ci(items,a)
 by={v:summary([x for x in a if x['venue']==v]) for v in ['seoul','busan','jeju']}
 # Confirm a fixed, previously chosen rule on different dates. No test-based threshold search.
 approved=bool(policy and len(a)>=80 and .1<=len(a)/len(items)<=.7 and ci[0]>0)
 venues=policy.get('venues',[]) if approved else []
 if any(by[v]['races']<25 for v in venues):approved=False;venues=[]
 return {'approved':approved and bool(venues),'approved_venues':venues,'criteria':policy,'selected':s,
  'all':summary(items),'coverage':len(a)/len(items),'uplift_95ci':ci,'by_venue':by}

def run(input_path,out):
 raw=Path(input_path).read_bytes();raw=gzip.decompress(raw) if input_path.endswith('.gz') else raw
 inputrows=[json.loads(x) for x in raw.splitlines() if x.strip()];rows,issues=validate_rows(inputrows)
 if not rows or min(x['date'] for x in rows)>'20210131':raise ValueError('Expanded 2021 history required')
 prepared,context=prepare(rows);usable=[r for r in prepared if r['date']>='20220101']
 comparison={};fitted={};models={};policies={};details={};calibrators={};parity=[];deployment={}
 incumbent=json.loads(Path('data/training-report.json').read_text())
 legacy=legacy_prepare(rows);legacy_audit=[r for r in legacy if r['date']>='20260716']
 out=Path(out);out.mkdir(parents=True,exist_ok=True)
 for kind in ['place','pair']:
  scores=[]
  for config in CONFIGS:
   folds=[]
   for begin,end in FOLDS:
    test=[r for r in usable if begin<=r['date']<end];m,n=fit(usable,kind,config,begin)
    metrics=summary(predictions(m,test,kind));folds.append(dict(metrics,from_date=begin,to_date=end,training_races=n))
    print(kind,config['name'],begin,metrics,flush=True)
   total=sum(x['races'] for x in folds);rate=sum(x['hits'] for x in folds)/total;brier=sum(x['brier']*x['races'] for x in folds)/total
   scores.append({'config':config,'folds':folds,'hit_rate':rate,'brier':brier})
  winner=max(scores,key=lambda x:(x['hit_rate'],-x['brier']));comparison[kind]={'candidates':scores,'chosen':winner['config']['name']}
  # Freeze the model before all 2026 calibration, policy selection and confirmation periods.
  m,n=fit(usable,kind,winner['config'],'20260101');fitted[kind]=n
  calrows=[r for r in usable if '20260101'<=r['date']<'20260301'];cal=calibration(m,calrows,kind)
  model=export_model(m);calibrators[kind]=cal;models[kind]=model
  checkrows=[r for r in usable if '20260101'<=r['date']<'20260115'][:4];X,_,_,_=package(checkrows,kind)
  assert np.max(np.abs(predict_export(model,X)-m.predict_proba(X)[:,1]))<1e-10
  parity.append({'kind':kind,'X':X[:30].tolist(),'probabilities':m.predict_proba(X[:30])[:,1].tolist()})
  choose=predictions(m,[r for r in usable if '20260301'<=r['date']<'20260501'],kind,cal)
  confirm=predictions(m,[r for r in usable if '20260501'<=r['date']<'20260716'],kind,cal)
  audit=predictions(m,[r for r in usable if r['date']>='20260716'],kind,cal)
  policy=choose_policy(choose);checked=validate_policy(policy,confirm)
  audit_selected=[x for x in audit if checked['approved'] and x['venue'] in checked['approved_venues'] and matches(x,policy)]
  checked.update(selection_period=summary(choose),audit_all=summary(audit),audit_selected=summary(audit_selected),audit_coverage=len(audit_selected)/len(audit),audit_reliability=reliability(audit))
  policies[kind]=checked;details[kind]={'selection':choose,'confirmation':confirm,'audit':audit}
  old=incumbent_predictions(legacy_audit,np.array(incumbent['weights']),kind)
  ci=paired_ci(old,audit)
  deployment[kind]={'approved':summary(audit)['hit_rate']>=summary(old)['hit_rate'] and ci[0]>=-.02,
   'incumbent':summary(old),'candidate':summary(audit),'paired_uplift_95ci':ci,
   'statistically_improved':ci[0]>0,
   'rule':'Candidate hit rate must not decrease and date-bootstrap lower bound must be >= -2 percentage points on reused audit; this is a deployment guard, not independent proof.'}
  details[kind]['incumbent_audit']=old
  print('FIXED POLICY',kind,checked,flush=True)
 report={'schema':2,'model':VERSION,'feature_version':VERSION,'features':FEATURES,'pair_columns':PAIR_COLUMNS,
  'approved':any(x['approved'] for x in deployment.values()),'deployment':deployment,'incumbent_model':incumbent['model'],
  'models':models,'calibrators':calibrators,'policies':policies,'comparison':comparison,
  'counts':{'source_races':len(inputrows),'collected_races':len(rows),'horse_starts':sum(len(r['horses']) for r in rows),'excluded_races':len(issues),
   'warmup_races':sum(r['date']<'20220101' for r in rows),'training_races':fitted,
   'calibration_races':sum('20260101'<=r['date']<'20260301' for r in usable),'selection_races':len(details['place']['selection']),
   'confirmation_races':len(details['place']['confirmation']),'audit_races':len(details['place']['audit'])},
  'period':{'from':min(r['date'] for r in rows),'to':max(r['date'] for r in rows),'fit_before':'20260101','calibration':'20260101–20260228','selection':'20260301–20260430',
   'confirmation':'20260501–20260715','audit':'20260716–'+max(r['date'] for r in rows)},
  'quality':{'by_year':dict(Counter(r['date'][:4] for r in rows)),'by_venue':dict(Counter(r['venue'] for r in rows)),'exclusions':issues,
   'timed_starts':sum(h.get('race_seconds') is not None for r in rows for h in r['horses'])},
  'dataset_sha256':hashlib.sha256(raw).hexdigest(),'limitations':['Retrospective evaluation only; no prospective performance claim.',
   'The Jul–Sep 2026 audit overlaps the former v5 test and is explicitly reused.',
   'Policy confirmation was separated from policy fitting; venue subgroups are descriptive, not independently significant.',
   'No odds, current body weight, current track condition or same-day results are model inputs.',
   'Horse identity uses venue and name; renamed or transferred horses may have incomplete history.',
   'Ambiguous results, ties and DNFs are excluded; selection bias may remain.',
   'Historic clocks use previous dates by venue/distance/track; this is not an official speed index.']}
 manifest_path=Path('training/manifest.json')
 if manifest_path.exists():
  manifest=json.loads(manifest_path.read_text())
  report['quality'].update(source_reports=len(manifest.get('reports',[])),download_errors=len(manifest.get('errors',[])),parser_excluded_races=sum(len(x.get('skips',[])) for x in manifest.get('reports',[])))
 report['serving']={'all_candidates':'Incumbent unless the all-race deployment guard passes.',
  'selective_candidates':'Separate candidate and record from the model whose frozen selection policy passes confirmation.','independent_tracks':True}
 (out/'model-v6.json').write_text(json.dumps(report,ensure_ascii=False,separators=(',',':')))
 (out/'history-context.json').write_text(json.dumps(context.export(),ensure_ascii=False,separators=(',',':')))
 (out/'evaluation-v6.json').write_text(json.dumps(details,ensure_ascii=False,separators=(',',':')))
 (out/'parity-v6.json').write_text(json.dumps(parity,separators=(',',':')))
 print('COMPLETE',report['counts'],flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--input',default='training/history.jsonl.gz');p.add_argument('--output',default='data');a=p.parse_args();run(a.input,a.output)
