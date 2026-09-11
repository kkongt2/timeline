const assert=require('node:assert/strict'),fs=require('fs'),vm=require('vm');
const root=require('node:path').resolve(__dirname,'..')+'/';
const {analyze,probs}=require(root+'model.js');
for(const n of [3,7,8,12]){const p=probs(Array(n).fill(1),n<=7?2:3),q=probs(Array(n).fill(1),3);assert(Math.abs(p.p.reduce((a,b)=>a+b,0)-(n<=7?2:3))<1e-9);assert(Math.abs(Object.values(q.q).reduce((a,b)=>a+b,0)-3)<1e-9);assert(Math.abs(q.q['0-1']-6/(n*(n-1)))<1e-9);}
const doc=JSON.parse(fs.readFileSync(root+'data/latest.json','utf8'));
for(const r of doc.races){const a=analyze(r);assert(a.places.every(x=>Number.isFinite(x.prob)&&x.prob>=0&&x.prob<=1.000001));assert(a.pairs.every(x=>Number.isFinite(x.prob)&&x.prob>=0&&x.prob<=1.000001));}
const r=doc.races[0],a=analyze(r),no=a.places.at(-1).numbers[0],o={place:{[no]:100},qpl:{}};
assert.deepEqual(analyze(r,'accuracy',o).places.map(x=>x.numbers),a.places.map(x=>x.numbers));
assert.equal(analyze(r,'value',o).places[0].numbers[0],no);
assert(analyze(r,'value',o).places.slice(1).every(x=>x.ev===null));
const nodes={},venues=['seoul','busan','jeju'].map(venue=>({dataset:{venue},classList:{toggle(){}},setAttribute(){}}));
function node(){return {textContent:'',innerHTML:'',value:'',hidden:false,disabled:false,dataset:{},classList:{toggle(){}},setAttribute(){},addEventListener(type,f){this[type]=f},insertAdjacentHTML(){},focus(){}}}
const html=fs.readFileSync(root+'index.html','utf8');for(const m of html.matchAll(/id="([^"]+)"/g))nodes['#'+m[1]]=node();nodes['#mode'].value='accuracy';
const storage=new Map(),sandbox={console,Intl,Date,Math,Number,Set,JSON,Array,String,Error,Infinity,localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)},document:{querySelector:s=>{assert(nodes[s],'Missing DOM '+s);return nodes[s]},querySelectorAll:()=>venues},fetch:async url=>({ok:true,json:async()=>url.includes('model-v6')?JSON.parse(fs.readFileSync(root+'data/model-v6.json')):url.includes('training-report')?JSON.parse(fs.readFileSync(root+'data/training-report.json')):doc}),alert:m=>{throw Error(m)}};
vm.createContext(sandbox);vm.runInContext(fs.readFileSync(root+'model.js','utf8'),sandbox);vm.runInContext(fs.readFileSync(root+'app.js','utf8'),sandbox);
(async()=>{
 await new Promise(setImmediate);
 const available=vm.runInContext("races.filter(r=>start(r)>Date.now()).filter(r=>analyze(r).selection.place.qualified)",sandbox);
 assert(available.length,'At least one real future race must exercise the qualified path');
 sandbox.qualifiedFixture=available.find(r=>{const a=vm.runInContext('analyze',sandbox)(r);return a.selectivePicks.place.numbers[0]!==a.places[0].numbers[0]})||available[0];
 vm.runInContext('source={updated_at:new Date().toISOString()};select(qualifiedFixture);save();',sandbox);
 assert(nodes['#placeLead'].innerHTML.includes('선별용 모델 후보'));assert(nodes['#raceOverview'].innerHTML.includes('selected-tag'));
 let saved=JSON.parse(storage.values().next().value);assert(saved[0].place.selected_pick);assert.equal(saved[0].place.selected_pick.model,'6.0-conditions');
 const separate=saved[0].place.selected_pick.numbers[0]!==saved[0].place.numbers[0];
 vm.runInContext(`let a=records(),x=a[0];const chosen=x.place.selected_pick.numbers[0],ordinary=x.place.numbers[0];const finish=[chosen,...x.field.filter(n=>n!==chosen&&n!==ordinary)].slice(0,3);x.result={finish,placeWinners:finish.slice(0,x.k),placeHit:finish.slice(0,x.k).includes(ordinary),pairHit:x.pair.numbers.every(n=>finish.includes(n)),placeOdds:null,pairOdds:null};put(a);renderHistory();`,sandbox);
 assert(nodes['#stats'].innerHTML.includes('선별 후보<b>100.0%'));
 if(separate)assert(nodes['#stats'].innerHTML.includes('전체 후보<b>0.0%'));
 vm.runInContext("source.updated_at='2000-01-01T00:00:00Z';render();",sandbox);
 assert(!nodes['#placeLead'].innerHTML.includes('선별용 모델 후보'));assert(!nodes['#raceOverview'].innerHTML.includes('selected-tag'));assert(nodes['#savePrediction'].disabled);
 nodes['#demoBtn'].onclick();assert(!nodes['#placeLead'].innerHTML.includes('선별용 모델 후보'));assert(nodes['#savePrediction'].disabled);
 console.log('PASS real-model UI, separate general/selected picks and result accounting, stale badge expiration and demo exclusion');
})().catch(e=>{console.error(e);process.exitCode=1});
