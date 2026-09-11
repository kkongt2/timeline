"""Frozen ablation: outcome/identity features versus additional race pace.

All historical checks are explicitly reused retrospective evidence. Prospective
archives start only after deployment and are never backfilled with these rows.
"""
import gzip,hashlib,json
from pathlib import Path
import numpy as np
import train_v6 as common
from features_v7 import FEATURES,VERSION,PAIR_COLUMNS,PAIR_EXTRA,prepare

MODE='pace'

def pair_features(X):
    pairs=np.array([(i,j) for i in range(len(X)) for j in range(i+1,len(X))]);out=[]
    for i,j in pairs:
        a,b=X[i],X[j];others=np.array([x for k,x in enumerate(X) if k not in (i,j)])
        extras=[max(others[:,30]),np.mean(others[:,30]),np.mean(others[:,30]>min(a[30],b[30])),
            max(others[:,4]),max(others[:,32]),np.mean(others[:,42]),a[42]*b[42],abs(a[43]-b[43]),
            min(a[41],b[41]),np.mean((others[:,42]>.5)&(others[:,46]>0))]
        out.append([*((a[PAIR_COLUMNS]+b[PAIR_COLUMNS])/2),*np.minimum(a[PAIR_COLUMNS],b[PAIR_COLUMNS]),
                    *np.abs(a[PAIR_COLUMNS]-b[PAIR_COLUMNS]),*a[20:27],*extras])
    return np.asarray(out),pairs

def package(rows,kind):
    xx=[];yy=[];ww=[];segments=[];offset=0
    for r in rows:
        X=np.asarray(r['X']).copy()
        if MODE=='core':X[:,40:48]=0
        truth=set(r['place_winners']) if kind=='place' else set(r['numbers'][i] for i in r['order'][:3])
        if kind=='place':numbers=[[n] for n in r['numbers']]
        else:
            X,ij=pair_features(X);numbers=[[r['numbers'][i],r['numbers'][j]] for i,j in ij]
        Y=np.array([all(n in truth for n in ns) for ns in numbers],int)
        segments.append(dict(race=r,lo=offset,hi=offset+len(X),numbers=numbers));offset+=len(X)
        xx.append(X);yy.append(Y);ww.extend([1/len(X)]*len(X))
    return np.concatenate(xx),np.concatenate(yy),np.asarray(ww),segments


def run():
    global MODE
    raw=gzip.decompress(Path('training/history-v7.jsonl.gz').read_bytes());rows=[json.loads(line) for line in raw.splitlines()]
    # Include only races compatible with the product's supported winner rules.
    # Keep payout-rule mismatches explicitly reported, never silently relabel them.
    rejected=[r for r in rows if r['place_k']!=(2 if len(r['horses'])<=7 else 3)]
    rows=[r for r in rows if r not in rejected]
    prepared,history=prepare(rows);usable=[r for r in prepared if r['date']>='20220101'];common.package=package
    development=[r for r in usable if '20250701'<=r['date']<'20260101']
    calrows=[r for r in usable if '20260101'<=r['date']<'20260301']
    auditrows=[r for r in usable if r['date']>='20260716']
    legacy=common.legacy_prepare(rows);legacy_audit=[r for r in legacy if r['date']>='20260716']
    incumbent=json.loads(Path('data/training-report.json').read_text());models={};cals={};modes={};comparisons={};deployment={};details={};parity=[];training={}
    for kind in ('place','pair'):
        config=dict(kind='tree',years=0 if kind=='place' else 3,half_life=0)
        scores=[]
        for mode in ('core','pace'):
            MODE=mode;m,n=common.fit(usable,kind,config,'20250701');metrics=common.summary(common.predictions(m,development,kind))
            scores.append(dict(mode=mode,**metrics));print('DEVELOPMENT',kind,mode,metrics,flush=True)
        winner=max(scores,key=lambda x:(x['hit_rate'],-x['brier']));MODE=winner['mode'];modes[kind]=MODE;comparisons[kind]=scores
        m,n=common.fit(usable,kind,config,'20260101');training[kind]=n
        cal=common.calibration(m,calrows,kind);cals[kind]=cal;models[kind]=common.export_model(m)
        predictions=common.predictions(m,auditrows,kind,cal);old=common.incumbent_predictions(legacy_audit,np.asarray(incumbent['weights']),kind)
        new_stats,old_stats=common.summary(predictions),common.summary(old);ci=common.paired_ci(old,predictions)
        # Conservative, fixed gate. Failure keeps production recommendations unchanged.
        approved=ci[0]>0 and new_stats['brier']<=old_stats['brier'] and len(predictions)>=300
        deployment[kind]=dict(approved=bool(approved),incumbent=old_stats,candidate=new_stats,paired_uplift_95ci=ci,
            reason='Retrospective date-bootstrap lower bound must be > 0, Brier must not worsen, and at least 300 paired races are required. No prospective claim.')
        details[kind]=dict(candidate=predictions,incumbent=old)
        X,_,_,_=package(calrows[:2],kind)
        assert np.max(np.abs(common.predict_export(models[kind],X)-m.predict_proba(X)[:,1]))<1e-10
        parity.append(dict(kind=kind,X=X[:30].tolist(),raw=m.predict_proba(X[:30])[:,1].tolist()))
        print('AUDIT',kind,deployment[kind],flush=True)
    quality=json.loads(Path('training/quality-v7.json').read_text())
    report=dict(schema=3,model=VERSION,feature_version=VERSION,features=FEATURES,pair_columns=PAIR_COLUMNS,pair_extra=PAIR_EXTRA,
        models=models,calibrators=cals,feature_modes=modes,comparison=comparisons,deployment=deployment,
        dataset_sha256=hashlib.sha256(raw).hexdigest(),counts=dict(races=len(rows),horse_starts=sum(len(r['horses']) for r in rows),
            training=training,development=len(development),calibration=len(calrows),audit=len(auditrows),payout_rule_exclusions=len(rejected)),
        quality={k:v for k,v in quality.items() if k not in ('samples','exclusions')},
        periods=dict(fit_before='20260101',development='20250701–20251231',calibration='20260101–20260228',audit='20260716–'+max(r['date'] for r in rows)),
        limitations=['Retrospective dates were used in earlier research; this is reused evidence, not an independent test.',
        'Ambiguous finish orders and unsupported payout rules remain excluded.',
        'Permanent horse IDs are retained where available; historical reports use venue, name, birth cohort and sex. Renames may split history.',
        'Missing sectionals are flagged; no odds or current-race outcomes are model inputs.'])
    fixtures=[]
    for r in calrows[:3]:
        h=sorted(r['horses'],key=lambda h:h['number'])
        fixture={k:r[k] for k in ('date','venue','race_no','distance','grade')};fixture.update(feature_version_v7=VERSION,history_through_v7='20251231',horses=[])
        for horse,x,q in zip(h,r['X'],r['quality']):fixture['horses'].append(dict(number=horse['number'],name=horse['name'],features_v7=x,quality_v7=q))
        expected={}
        for kind in ('place','pair'):
            MODE=modes[kind];X,y,w,segs=package([r],kind);rawp=common.predict_export(models[kind],X);c=cals[kind]
            pp=common.expit(c['a']*common.logit(np.clip(rawp,1e-6,1-1e-6))+c['b']);expected[kind]=[dict(numbers=nums,prob=float(p)) for nums,p in zip(segs[0]['numbers'],pp)]
        fixtures.append(dict(race=fixture,expected=expected))
    Path('data/model-v7.json').write_text(json.dumps(report,ensure_ascii=False,separators=(',',':')))
    Path('data/evaluation-v7.json').write_text(json.dumps(details,ensure_ascii=False,separators=(',',':')))
    Path('data/parity-v7.json').write_text(json.dumps(dict(estimators=parity,fixtures=fixtures),ensure_ascii=False,separators=(',',':')))
    Path('data/history-context-v7.json.gz').write_bytes(gzip.compress(json.dumps(history.export(),ensure_ascii=False,separators=(',',':')).encode(),mtime=0))
    print('COMPLETE',report['counts'],flush=True)

if __name__=='__main__':run()
