const assert=require('node:assert/strict'),fs=require('node:fs'),zlib=require('node:zlib');
const api=require('../model.js'),read=p=>JSON.parse(fs.readFileSync(p,'utf8'));
const model=read('data/model.json'),fixture=read('data/parity.json'),report=read('data/backtest.json');
const race={date:'20260102',history_through_v7:'20251231',feature_version_v7:model.feature_version,horses:fixture.horses};
const actual=api.predict(race,model);assert.equal(actual.length,fixture.expected.length);
for(const expected of fixture.expected){const a=actual.find(c=>c.numbers.join('-')===expected.numbers.join('-'));assert.ok(Math.abs(a.prob-expected.prob)<1e-10);assert.ok(Math.abs(a.dividend-expected.dividend)<1e-8);assert.ok(Math.abs(a.break_even*a.prob-1)<1e-12);}
assert.deepEqual(api.predict({...race,horses:[...race.horses].reverse()},model),actual);
assert.equal(api.predict({...race,history_through_v7:'20260102'},model).length,0);
assert.equal(api.predict({...race,history_through_v7:'20250101'},model).length,0);
assert.equal(api.predict({...race,horses:race.horses.slice(1)},model).length,0);
assert.equal(api.predict({...race,horses:race.horses.map((h,i)=>i? h:{...h,features_v7:undefined})},model).length,0);
assert.deepEqual(model.policy,report.policy);assert.equal(model.approved,report.approved);
const bets=read('data/backtest-bets.json'),payouts=JSON.parse(zlib.gunzipSync(fs.readFileSync('training/payouts.json.gz')));
const index=new Map(payouts.map(r=>[`${r.date}/${r.venue}/${r.race_no}`,r.payouts]));let profit=0;
for(const b of bets){assert.ok(b.date>='20260101'&&b.date<='20260910');const p=index.get(`${b.date}/${b.venue}/${b.race_no}`);assert.ok(p);assert.equal(b.gross,p[b.numbers.join('-')]||0);assert.ok(b.edge>=model.policy.min_edge);profit+=(b.gross-1)*1000;}
assert.equal(Math.round(profit),report.evaluation.profit_krw);assert.equal(bets.length*1000,report.evaluation.stake_krw);
const e=report.evaluation,s=report.selection;
assert.equal(model.approved,s.profit_units>0&&e.bets>=200&&e.dates>=60&&e.roi_95ci[0]>0&&e.without_best_day_profit_krw>0);
console.log('PASS model parity, permutation, feature guards, equal-stake accounting, official dividend labels and deployment gate');
