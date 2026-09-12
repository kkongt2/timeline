"""One frozen profit experiment. Do not retune after viewing the 2026 evaluation.

Realized final dividends are outcomes only. Every feature uses strictly earlier
race dates. Equal 1,000 KRW per selected combination; no compounding/chasing.
"""
import gzip, hashlib, json
from collections import defaultdict
from pathlib import Path
import numpy as np
from scipy.special import expit, logit
from sklearn.ensemble import HistGradientBoostingClassifier,HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression
from features_v7 import prepare,FEATURES,PAIR_COLUMNS,VERSION
from profit_model import pair_features,export

SEED=20260912
EXPERIMENT=dict(train=['20220101','20241231'],calibrate=['20250101','20250331'],
    selection=['20250401','20251231'],evaluation=['20260101','20260910'],
    dividend_losses=['gamma','poisson'],min_edges=[0,.05,.1,.2,.35,.5,.75,1.0],max_per_race=[1,2,3],
    min_selection_bets=200,min_selection_dates=60,unit_stake_krw=1000,
    objective='maximum total settled pre-tax net profit at equal stake per combination',
    deployment_gate='selection profit > 0; evaluation >=200 bets and >=60 dates; date-bootstrap 95% ROI lower bound >0; profit remains >0 without best day')

def choose(races,policy):
    out=[]
    for r in races:
        eligible=[c for c in r['candidates'] if c['edge']>=policy['min_edge']]
        ordered=sorted(eligible,key=lambda c:(-c['edge'],c['numbers']))[:policy['max_per_race']]
        out.extend(dict(c,date=r['date'],venue=r['venue'],race_no=r['race_no']) for c in ordered)
    return out

def stats(bets,ci=False):
    days=defaultdict(lambda:[0.,0]);races=defaultdict(float);months=defaultdict(lambda:[0.,0]);losses=streak=0
    for b in bets:
        profit=b['gross']-1;days[b['date']][0]+=profit;days[b['date']][1]+=1
        races[(b['date'],b['venue'],b['race_no'])]+=profit
        months[b['date'][:6]][0]+=profit;months[b['date'][:6]][1]+=1
        streak=streak+1 if not b['gross'] else 0;losses=max(losses,streak)
    n=len(bets);net=sum(b['gross']-1 for b in bets);equity=peak=drawdown=0.;curve=[];losing_days=day_streak=0
    for day,(p,count) in sorted(days.items()):
        equity+=p;peak=max(peak,equity);drawdown=max(drawdown,peak-equity)
        curve.append(dict(date=day,profit_units=round(equity,4)))
        day_streak=day_streak+1 if p<0 else 0;losing_days=max(losing_days,day_streak)
    out=dict(bets=n,races=len(races),dates=len(days),stake_krw=n*1000,return_krw=round((net+n)*1000),
        profit_krw=round(net*1000),profit_units=round(net,6),roi=net/n if n else None,
        hit_rate=sum(b['gross']>0 for b in bets)/n if n else None,
        mean_hit_dividend=float(np.mean([b['gross'] for b in bets if b['gross']])) if any(b['gross'] for b in bets) else None,
        daily_max_drawdown_krw=round(drawdown*1000),max_losing_bet_streak=losses,max_losing_days=losing_days,
        without_best_day_profit_krw=round((net-max((v[0] for v in days.values()),default=0))*1000),
        months=[dict(month=m,profit_krw=round(p*1000),bets=int(c),roi=p/c) for m,(p,c) in sorted(months.items())],curve=curve)
    if ci:
        rng=np.random.default_rng(SEED);a=np.array(list(days.values()));values=[]
        if len(a):
            for _ in range(2500):
                sample=a[rng.integers(0,len(a),len(a))].sum(axis=0);values.append(sample[0]/sample[1])
        out['roi_95ci']=np.quantile(values,[.025,.975]).tolist() if values else [None,None]
    return out

def run():
    Path('data').mkdir(exist_ok=True)
    Path('data/experiment.json').write_text(json.dumps(EXPERIMENT,indent=2))
    raw=Path('training/history-v7.jsonl.gz').read_bytes();pp=Path('training/payouts.json.gz').read_bytes()
    rows=[json.loads(x) for x in gzip.decompress(raw).splitlines()]
    payout_rows=json.loads(gzip.decompress(pp));payouts={(r['date'],r['venue'],r['race_no']):r['payouts'] for r in payout_rows}
    prepared,history=prepare(rows);del history
    use=[r for r in prepared if '20220101'<=r['date']<='20260910' and (r['date'],r['venue'],r['race_no']) in payouts]
    xx=[];yy=[];segs=[];offset=0
    for r in use:
        X,ij=pair_features(r['X']);nums=[sorted([r['numbers'][i],r['numbers'][j]]) for i,j in ij]
        payout=payouts[(r['date'],r['venue'],r['race_no'])]
        y=[payout.get('-'.join(map(str,n)),0) for n in nums]
        xx.append(X.astype(np.float32));yy.extend(y)
        segs.append(dict(date=r['date'],venue=r['venue'],race_no=r['race_no'],numbers=nums,lo=offset,hi=offset+len(X)))
        offset+=len(X)
    X=np.concatenate(xx);del xx;gross=np.array(yy);y=(gross>0).astype(int)
    dates=np.empty(len(y),dtype='U8')
    for s in segs:dates[s['lo']:s['hi']]=s['date']
    fit=dates<'20250101';cal=(dates>='20250101')&(dates<'20250401')
    print('MATRIX',X.shape,'fit',int(fit.sum()),'cal',int(cal.sum()),flush=True)
    classifier=HistGradientBoostingClassifier(max_iter=110,max_leaf_nodes=7,min_samples_leaf=100,learning_rate=.06,l2_regularization=10,early_stopping=False,random_state=SEED)
    classifier.fit(X[fit],y[fit]);p=classifier.predict_proba(X)[:,1]
    c=LogisticRegression(C=100).fit(logit(np.clip(p[cal],1e-6,1-1e-6)).reshape(-1,1),y[cal])
    a=max(.01,float(c.coef_[0,0]));b=float(c.intercept_[0]);p=expit(a*logit(np.clip(p,1e-6,1-1e-6))+b)
    options=[];models={};preds={};scales={}
    # Evaluation labels never enter model selection or calibration.
    for loss in EXPERIMENT['dividend_losses']:
        reg=HistGradientBoostingRegressor(loss=loss,max_iter=110,max_leaf_nodes=7,min_samples_leaf=100,learning_rate=.06,l2_regularization=10,early_stopping=False,random_state=SEED)
        hitfit=fit&(y==1);reg.fit(X[hitfit],gross[hitfit]);d=reg.predict(X)
        hitcal=cal&(y==1);scale=float(gross[hitcal].sum()/d[hitcal].sum());d=np.maximum(1,d*scale)
        predictions=[]
        for s in segs:
            if s['date']<'20250401':continue
            candidates=[dict(numbers=ns,prob=float(p[i]),dividend=float(d[i]),edge=float(p[i]*d[i]-1),gross=float(gross[i])) for i,ns in zip(range(s['lo'],s['hi']),s['numbers'])]
            predictions.append(dict(date=s['date'],venue=s['venue'],race_no=s['race_no'],candidates=candidates))
        selection=[r for r in predictions if r['date']<'20260101']
        models[loss]=reg;preds[loss]=predictions;scales[loss]=scale
        for edge in EXPERIMENT['min_edges']:
            for k in EXPERIMENT['max_per_race']:
                policy=dict(dividend_loss=loss,min_edge=edge,max_per_race=k)
                s=stats(choose(selection,policy));eligible=s['bets']>=200 and s['dates']>=60
                options.append(dict(policy=policy,eligible=eligible,selection={k:v for k,v in s.items() if k not in ('curve','months')}))
        print('FITTED',loss,'scale',scale,flush=True)
    eligible=[o for o in options if o['eligible']]
    if not eligible:raise ValueError('No policy has sufficient selection support')
    chosen=max(eligible,key=lambda o:(o['selection']['profit_units'],-o['selection']['bets']))
    policy=chosen['policy'];loss=policy['dividend_loss']
    # Freeze choice to disk before computing ANY evaluation statistic.
    Path('data/frozen-policy.json').write_text(json.dumps(dict(experiment=EXPERIMENT,chosen=chosen,options=options),indent=2))
    selection=stats(choose([r for r in preds[loss] if r['date']<'20260101'],policy),True)
    test=[r for r in preds[loss] if r['date']>='20260101'];bets=choose(test,policy);evaluation=stats(bets,True)
    baseline=[]
    for r in test:
        v=max(r['candidates'],key=lambda c:c['prob']);baseline.append(dict(v,date=r['date'],venue=r['venue'],race_no=r['race_no']))
    approved=bool(selection['profit_units']>0 and evaluation['bets']>=200 and evaluation['dates']>=60 and evaluation['roi_95ci'][0]>0 and evaluation['without_best_day_profit_krw']>0)
    report=dict(schema=1,name='QPL flat-stake profit v1',objective=EXPERIMENT['objective'],unit_stake_krw=1000,policy=policy,
        approved=approved,selection=selection,evaluation=evaluation,baseline=stats(baseline,True),
        by_venue={v:stats([x for x in bets if x['venue']==v],True) for v in ['seoul','busan','jeju']},
        counts=dict(history_races=len(rows),payout_races=len(payout_rows),used_races=len(use),pairs=len(y),
            fit_races=sum(s['date']<'20250101' for s in segs),calibration_races=sum('20250101'<=s['date']<'20250401' for s in segs),
            selection_races=sum('20250401'<=s['date']<'20260101' for s in segs),evaluation_races=len(test),searched_policies=len(options)),
        experiment=EXPERIMENT,dataset_sha256=hashlib.sha256(raw+pp).hexdigest(),
        limitations=['Retrospective reconstruction, not actual pre-race prediction records.',
        '2026 dates appeared in earlier accuracy research; held out from this profit experiment, not globally untouched.',
        'Final dividends are labels only. Displayed dividend is a model estimate, not a live market quote.',
        'Pre-tax returns after subtracting each stake; official dividends already reflect the betting-pool deduction. Personal payout tax and admission costs are not included.',
        'Ambiguous finish orders and unverified or missing dividends are excluded. No missing result is labeled a loss.',
        'Two models and 48 policies are a bounded search, not proof of the globally most profitable strategy.',
        'Daily drawdown ignores intraday ordering. Multiple combinations in a race are correlated.'])
    model=dict(schema=1,feature_version=VERSION,features=FEATURES,pair_columns=PAIR_COLUMNS,
        classifier=export(classifier,'sigmoid'),dividend=export(models[loss],'exp'),calibrator=dict(a=a,b=b),
        dividend_scale=scales[loss],policy=policy,approved=approved,fit_before='20250101',evaluation_end='20260910')
    Path('data/model.json').write_text(json.dumps(model,separators=(',',':')))
    Path('data/backtest.json').write_text(json.dumps(report,ensure_ascii=False,separators=(',',':')))
    Path('data/backtest-bets.json').write_text(json.dumps(bets,separators=(',',':')))
    fixture=next(r for r in use if r['date']>='20260101');FX,ij=pair_features(fixture['X'])
    fp=expit(a*logit(classifier.predict_proba(FX)[:,1])+b);fd=np.maximum(1,models[loss].predict(FX)*scales[loss])
    Path('data/parity.json').write_text(json.dumps(dict(horses=[dict(number=n,features_v7=x) for n,x in zip(fixture['numbers'],fixture['X'])],expected=[dict(numbers=sorted([fixture['numbers'][i],fixture['numbers'][j]]),prob=float(pr),dividend=float(di)) for (i,j),pr,di in zip(ij,fp,fd)]),separators=(',',':')))
    print('COMPLETE',json.dumps({k:report[k] for k in ['approved','policy','counts']},ensure_ascii=False),flush=True)
    print('SELECTION',selection['profit_krw'],selection['roi'],'EVALUATION',evaluation['profit_krw'],evaluation['roi'],evaluation['roi_95ci'],flush=True)

if __name__=='__main__':run()
