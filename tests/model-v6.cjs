'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..');const model=require('../model.js');
const report=JSON.parse(fs.readFileSync(path.join(root,'data/model-v6.json')));
assert(model.setAdvancedModel(report));
const parity=JSON.parse(fs.readFileSync(path.join(root,'data/parity-v6.json')));
for(const p of parity)for(let i=0;i<p.X.length;i++)assert(Math.abs(model.predictEstimator(report.models[p.kind],p.X[i])-p.probabilities[i])<1e-10,'Python/JS estimator parity');
const live=JSON.parse(fs.readFileSync(path.join(root,'data/latest.json'))).races;
model.setTrainedModel(JSON.parse(fs.readFileSync(path.join(root,'data/training-report.json'))));
for(const r of live){
 const a=model.analyze(r),b=model.analyze({...r,horses:[...r.horses].reverse()});
 assert.deepEqual(a.places.map(x=>x.numbers),b.places.map(x=>x.numbers));assert.deepEqual(a.pairs.map(x=>x.numbers),b.pairs.map(x=>x.numbers));
 for(const kind of ['place','pair']){
  const items=kind==='place'?a.places:a.pairs;assert(items.every(x=>Number.isFinite(x.prob)&&x.prob>=0&&x.prob<=1.000001));
  if(a.selection[kind].qualified)assert(a.selectiveActive[kind]&&report.policies[kind].approved&&a.selectivePicks[kind]);
 }
 const stale=model.analyze({...r,history_through:'20200101'});assert(!stale.advanced.place&&!stale.advanced.pair);
 assert(!stale.selectivePicks.place&&!stale.selectivePicks.pair);
 const future=model.analyze({...r,history_through:r.date});assert(!future.advanced.place&&!future.advanced.pair);
 assert(!future.selectivePicks.place&&!future.selectivePicks.pair);
 const missing=structuredClone(r);delete missing.horses[0].features_v6;const fallback=model.analyze(missing);assert(!fallback.advanced.place&&!fallback.advanced.pair);
 assert(!fallback.selectivePicks.place&&!fallback.selectivePicks.pair);
 if(r.horses.length>3){const withdrawn=structuredClone(r);withdrawn.horses[0].withdrawn=true;assert(!model.analyze(withdrawn).advanced.place);assert(!model.analyze(withdrawn).selectivePicks.place);}
 const value=model.analyze(r,'value');assert(!value.selection.place.qualified&&!value.selection.pair.qualified);
}
const malformed=structuredClone(report);malformed.models.place={kind:'tree',bias:0,trees:[[[0,0,0,0,0,0]]]};assert.equal(model.setAdvancedModel(malformed),false);
console.log('PASS serialized Python/JS parity, field ordering, probability bounds, selection gates, stale/future/missing/withdrawn fallback and malformed-model rejection');
