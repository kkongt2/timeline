const assert=require('node:assert/strict'),fs=require('fs'),path=require('path');
const engine=require('../model-v7.js'),base=require('../model.js');
const root=path.resolve(__dirname,'..'),report=JSON.parse(fs.readFileSync(root+'/data/model-v7.json')),checks=JSON.parse(fs.readFileSync(root+'/data/parity-v7.json'));
assert(engine.configure(report));
for(const t of checks.estimators)for(let i=0;i<t.X.length;i++)assert(Math.abs(engine.predict(report.models[t.kind],t.X[i],{a:1,b:0})-t.raw[i])<1e-10);
for(const f of checks.fixtures){
 const a=engine.analyze(f.race);assert(a);
 for(const k of ['place','pair']){
  assert.equal(a[k].length,f.expected[k].length);
  for(const item of a[k]){const expected=f.expected[k].find(x=>x.numbers.join('-')===item.numbers.join('-'));assert(expected);assert(Math.abs(item.prob-expected.prob)<1e-10);}
 }
 const reversed=structuredClone(f.race);reversed.horses.reverse();assert.deepEqual(engine.analyze(reversed),a);
 assert.equal(engine.analyze({...f.race,history_through_v7:f.race.date}),null);
 assert.equal(engine.analyze({...f.race,history_through_v7:'20240101'}),null);
 assert.equal(engine.analyze({...f.race,horses:f.race.horses.slice(1)}),null);
 const altered=structuredClone(f.race);altered.horses[0].features_v7[0]=NaN;assert.equal(engine.analyze(altered),null);
 base.setChallengerModel(null);const before=base.analyze(f.race);
 base.setChallengerModel(report);const after=base.analyze(f.race);assert(after.challenger);
 for(const k of ['place','pair'])if(!report.deployment[k].approved)assert.deepEqual(before[k==='place'?'places':'pairs'],after[k==='place'?'places':'pairs']);
}
const bad=structuredClone(report);bad.features.reverse();assert.equal(engine.configure(bad),false);
const loop=structuredClone(report);loop.models.pair.trees[0][0]=[0,0,0,0,0,0];assert.equal(engine.configure(loop),false);
assert(engine.configure(report));
console.log('PASS Python/JS full race parity, pair rival features, ordering, missing/stale/withdrawn fallback, model validation and production gate');
