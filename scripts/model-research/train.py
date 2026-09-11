"""Fit a top-three Plackett-Luce model; retain an untouched chronological test period."""
import argparse, hashlib, json, math
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp

FEATURES=['place_1y','win_1y','distance_place','relative_rating','recent_form','jockey_place','trainer_place','relative_burden','body_change','interval']
BASE=np.array([2.10,.55,1.15,.75,.65,.35,.25,.18,.20,.10])*.6

def features(h,field):
 n=h['starts_1y'];w=h['wins_1y'];s=h['seconds_1y'];t=h['thirds_1y']
 norm=lambda v,a: (v-min(a))/(max(a)-min(a)) if max(a)>min(a) else .5
 rating=norm(h.get('rating',0),[x.get('rating',0) for x in field])
 burden=np.clip((np.mean([x['burden'] for x in field])-h['burden'])/5,-1,1)
 rec=h['recent_finishes'][:5];ww=[1-i*.09 for i in range(len(rec))]
 recent=sum(np.clip((8-p)/7,0,1)*v for p,v in zip(rec,ww))/sum(ww) if ww else .35
 body=-np.clip((abs(h['horse_weight_change'])/h['horse_weight']-.015)/.045,0,1) if h.get('horse_weight') and h.get('horse_weight_change') is not None else 0
 iw=h['interval_weeks'];interval=.15 if 2<=iw<=8 else (-.35 if iw>14 else 0)
 return [(w+s+t+1.2)/(n+4),(w+.35)/(n+4),(h['distance_top3']+.8)/(h['distance_starts']+3),rating,recent,norm(h['jp'],[x['jp'] for x in field]),norm(h['tp'],[x['tp'] for x in field]),burden,body,interval]

def prepare(rows):
 horses=defaultdict(list);people=defaultdict(list);prepared=[]
 for r in sorted(rows,key=lambda x:(x['date'],x['venue'],x['race_no'])):
  date=datetime.strptime(r['date'],'%Y%m%d');cut=date-timedelta(days=365);field=[]
  for h0 in sorted(r['horses'],key=lambda h:h['number']):
   h=dict(h0);hist=[x for x in horses[(r['venue'],h['name'])] if x[0]<date];year=[x for x in hist if x[0]>=cut];dist=[x for x in hist if x[2]==r['distance']]
   h.update(starts_1y=len(year),wins_1y=sum(x[1]==1 for x in year),seconds_1y=sum(x[1]==2 for x in year),thirds_1y=sum(x[1]==3 for x in year),distance_starts=len(dist),distance_top3=sum(x[1]<=3 for x in dist),recent_finishes=[x[1] for x in hist[-5:][::-1]],interval_weeks=(date-hist[-1][0]).days/7 if hist else 0)
   for kind,out in [('jockey','jp'),('trainer','tp')]:
    p=[x[1] for x in people[(r['venue'],kind,h[kind])] if cut<=x[0]<date];h[out]=sum(v<=3 for v in p)/len(p) if p else .3
   field.append(h)
  if date>=datetime(2025,1,1):
   # The full 2024 period is historical warm-up, never a training example.
   prepared.append(dict(r,X=np.array([features(h,field) for h in field]),order=np.argsort([h['finish'] for h in field]),form=field))
  for h in r['horses']:
   horses[(r['venue'],h['name'])].append((date,h['finish'],r['distance']))
   for kind in ['jockey','trainer']:people[(r['venue'],kind,h[kind])].append((date,h['finish']))
 return prepared

CHOICES={}
def objective(w,rows,ridge=0):
 key=id(rows)
 if key not in CHOICES:
  xx=[];yy=[];mm=[];width=max(len(r['X']) for r in rows)
  for r in rows:
   remaining=list(range(len(r['X'])))
   for winner in r['order'][:3]:
    a=np.zeros((width,len(w)));mask=np.zeros(width,dtype=bool);a[:len(remaining)]=r['X'][remaining];mask[:len(remaining)]=True
    xx.append(a);mm.append(mask);yy.append(r['X'][winner]);remaining.remove(winner)
  CHOICES[key]=(np.array(xx),np.array(yy),np.array(mm))
 X,Y,mask=CHOICES[key];z=np.einsum('ijk,k->ij',X,w);z=np.where(mask,z,-np.inf);ls=logsumexp(z,axis=1);p=np.exp(z-ls[:,None]);loss=np.sum(ls-Y@w)/len(rows)
 grad=(np.einsum('ij,ijk->k',p,X)-Y.sum(axis=0))/len(rows)
 return loss+ridge*np.sum(w*w)/2,grad+ridge*w

def probabilities(z,k):
 st=np.exp(np.clip(z-z.mean(),-4,4));T=st.sum();n=len(st);p=np.zeros(n);pair=np.zeros((n,n))
 for i in range(n):
  for j in range(n):
   if j==i:continue
   v=st[i]/T*st[j]/(T-st[i])
   if k==2:p[i]+=v;p[j]+=v
   for q in range(n):
    if q==i or q==j:continue
    v3=v*st[q]/(T-st[i]-st[j])
    if k==3:p[i]+=v3;p[j]+=v3;p[q]+=v3
    for a,b in [(i,j),(i,q),(j,q)]:pair[min(a,b),max(a,b)]+=v3
 return p,pair

def evaluate(rows,w):
 details=[]
 for r in rows:
  n=len(r['X']);k=r.get('place_k',2 if n<=7 else 3);z=r['X']@w;p,q=probabilities(z,k);i=int(np.argmax(p));a,b=np.unravel_index(np.argmax(q),q.shape);truth=set(r['order'][:k]);top3=set(r['order'][:3]);ys=np.array([j in truth for j in range(n)],float)
  details.append({'date':r['date'],'venue':r['venue'],'place':int(i in truth),'pair':int(a in top3 and b in top3),'brier':float(np.mean((p-ys)**2))})
 return {'races':len(rows),'place_hit_rate':float(np.mean([x['place'] for x in details])),'pair_hit_rate':float(np.mean([x['pair'] for x in details])),'brier':float(np.mean([x['brier'] for x in details]))},details

def run(input_path,out):
 raw=Path(input_path).read_bytes();rows=[json.loads(x) for x in raw.splitlines() if x.strip()];allrows=prepare(rows)
 train=[r for r in allrows if r['date']<'20260601'];valid=[r for r in allrows if '20260601'<=r['date']<'20260716'];test=[r for r in allrows if r['date']>='20260716']
 counts={'collected_races':len(rows),'training_races':len(train),'validation_races':len(valid),'test_races':len(test),'horse_starts':sum(len(r['horses']) for r in rows)}
 if len(train)<1000 or len(valid)<200 or len(test)<300:raise ValueError('Insufficient chronological coverage: '+str(counts))
 candidates=[]
 for ridge in [.001,.01,.1]:
  fit=minimize(lambda w:objective(w,train,ridge),BASE,jac=True,method='L-BFGS-B',bounds=[(-6,6)]*len(BASE),options={'maxiter':100,'ftol':1e-8});v=objective(fit.x,valid)[0];candidates.append((v,fit.x,ridge));print('candidate',ridge,v,fit.success,flush=True)
 _,w,ridge=min(candidates,key=lambda x:x[0]);base,bd=evaluate(test,BASE);candidate,cd=evaluate(test,w)
 # Paired bootstrap by date preserves within-meeting dependencies.
 byday=defaultdict(list)
 for b,c in zip(bd,cd):byday[b['date']].append((c['place']+c['pair']-b['place']-b['pair'])/2)
 days=sorted(byday);rng=np.random.default_rng(20260911);boots=[]
 for _ in range(2000):
  sample=rng.choice(days,len(days));values=[v for d in sample for v in byday[d]];boots.append(np.mean(values))
 ci=[float(x) for x in np.quantile(boots,[.025,.975])]
 approved=bool(ci[0]>0 and candidate['place_hit_rate']>=base['place_hit_rate'] and candidate['pair_hit_rate']>=base['pair_hit_rate'] and candidate['brier']<base['brier'])
 venue={v:{'baseline':evaluate([r for r in test if r['venue']==v],BASE)[0],'candidate':evaluate([r for r in test if r['venue']==v],w)[0]} for v in sorted(set(r['venue'] for r in test))}
 approved_venues=[v for v,x in venue.items() if approved and x['candidate']['races']>=100 and x['candidate']['place_hit_rate']>=x['baseline']['place_hit_rate'] and x['candidate']['pair_hit_rate']>=x['baseline']['pair_hit_rate'] and x['candidate']['brier']<x['baseline']['brier']]
 report={'approved_venues':approved_venues,'schema':1,'status':'validated_improvement' if approved else 'no_confirmed_improvement','model':'5.0-history','counts':counts,'period':{'from':min(r['date'] for r in rows),'to':max(r['date'] for r in rows),'train':'20250101–20260531','validation':'20260601–20260715','test':'20260716–'+max(r['date'] for r in rows)},'baseline':base,'candidate':candidate,'by_venue':venue,'paired_daily_bootstrap_95ci':ci,'ridge':ridge,'features':FEATURES,'weights':w.tolist(),'approved':approved,'dataset_sha256':hashlib.sha256(raw).hexdigest(),'source':'https://race.kra.co.kr/','limitations':['Historical replay, not prospective live validation.','No final odds or same-race results used as features.','Horse/person historical statistics reconstructed from earlier dates only.','Distance histories begin at collection start; not lifetime totals.','Abstention and returns are not evaluated; all eligible races are scored.','Horse identity uses venue and name; name changes are not linked.']}
 Path(out).mkdir(parents=True,exist_ok=True);Path(out,'training-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));Path(out,'candidate-model.json').write_text(json.dumps({'version':'5.0-history','weights':w.tolist(),'features':FEATURES,'approved':approved,'dataset_sha256':report['dataset_sha256']}));print(json.dumps(report,ensure_ascii=False),flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',default='data');a=p.parse_args();run(a.input,a.output)
