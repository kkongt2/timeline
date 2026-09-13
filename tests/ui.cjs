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
const storage=new Map(),sandbox={console,Intl,Date,Math,Number,Set,JSON,Array,String,Error,Infinity,localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)},document:{querySelector:s=>{assert(nodes[s],'Missing DOM '+s);return nodes[s]},querySelectorAll:()=>venues},fetch:async()=>({ok:true,json:async()=>doc}),alert:m=>{throw Error(m)}};
vm.createContext(sandbox);vm.runInContext(fs.readFileSync(root+'model.js','utf8'),sandbox);vm.runInContext(fs.readFileSync(root+'app.js','utf8'),sandbox);
(async()=>{await new Promise(setImmediate);nodes['#demoBtn'].onclick();assert(nodes['#placeLead'].innerHTML.includes('직접 입력 / 데모'));assert(nodes['#savePrediction'].disabled);
const future={...r,date:'20990101',start_time:'12:00'};sandbox.fixture=future;vm.runInContext('source={updated_at:new Date().toISOString()};select(fixture);save();save();',sandbox);assert.equal(JSON.parse(storage.values().next().value).length,1);
vm.runInContext("$('#mode').value='value';render();save();",sandbox);assert.equal(JSON.parse(storage.values().next().value).length,2);
vm.runInContext("select({...fixture,date:'20000101'});save();",sandbox);assert.equal(JSON.parse(storage.values().next().value).length,2);
vm.runInContext("source={updated_at:'2000-01-01T00:00:00Z'};select(fixture);",sandbox);assert(nodes['#savePrediction'].disabled);
sandbox.selectorFixtures=[{...r,venue:'seoul',date:'20300131',race_no:1},{...r,venue:'seoul',date:'20300131',race_no:2},{...r,venue:'seoul',date:'20300201',race_no:3},{...r,venue:'busan',date:'20300202',race_no:5}];
vm.runInContext("races=selectorFixtures;setVenue('seoul');$('#date').value='2030-01-31';$('#raceNo').value='1';chooseAvailable();",sandbox);
assert(nodes['#dateCalendar'].innerHTML.includes('data-date="20300131"'));assert(nodes['#calendarMonth'].innerHTML.includes('value="203002"'));assert(!nodes['#dateCalendar'].innerHTML.includes('data-date="20300201"'));assert(!nodes['#dateCalendar'].innerHTML.includes('20300202'));
nodes['#raceButtons'].click({target:{closest:()=>({dataset:{race:'2'}})}});assert.equal(vm.runInContext('current.race_no',sandbox),2);
nodes['#calendarMonth'].value='203002';nodes['#calendarMonth'].onchange();assert.equal(vm.runInContext('current.race_no',sandbox),3);assert.equal(nodes['#date'].value,'2030-02-01');
venues[1].onclick();assert.equal(nodes['#date'].value,'2030-02-02');assert.equal(vm.runInContext('current.race_no',sandbox),5);assert(!nodes['#dateCalendar'].innerHTML.includes('20300131'));
venues[2].onclick();assert(nodes['#analysis'].hidden);assert.equal(nodes['#date'].value,'');assert(!nodes['#raceButtons'].innerHTML.includes('data-race='));
nodes['#raceOverview'].click({target:{closest:()=>({dataset:{overviewRace:'5'}})}});
sandbox.archiveFixture={...r,date:'20000101',start_time:'',historical_view:true,official_result:{status:'confirmed',place:{status:'confirmed',payouts:[{numbers:[1],odds:1.5}]},pair:{status:'confirmed',payouts:[{numbers:[1,2],odds:3.2}]}}};
vm.runInContext('select(archiveFixture)',sandbox);assert(nodes['#placeLead'].innerHTML.includes('1.5배'));assert(nodes['#pairLead'].innerHTML.includes('3.2배'));assert(nodes['#savePrediction'].disabled);
sandbox.marketFixture={status:'confirmed',payouts:[{numbers:[2,1],odds:3.2}]};
assert.equal(vm.runInContext('matchingPayout(marketFixture,[1,2]).odds',sandbox),3.2);
assert.equal(vm.runInContext('Boolean(matchingPayout(marketFixture,[1,3]))',sandbox),false);
assert.equal(vm.runInContext('Boolean(matchingPayout({...marketFixture,status:"pending"},[1,2]))',sandbox),false);
assert.equal(vm.runInContext('Boolean(matchingPayout({...marketFixture,status:"refunded"},[1,2]))',sandbox),false);
assert(vm.runInContext('hitHTML(archiveFixture,"place",[1])',sandbox).includes('✓ 적중'));
assert.equal(vm.runInContext('hitHTML(archiveFixture,"place",[2])',sandbox),'');
assert(vm.runInContext('officialResultHTML(archiveFixture,"pair",[2,1])',sandbox).includes('result-hit'));
// A date present only in the calendar index is retrieved on selection.
sandbox.fetch=async()=>({ok:true,json:async()=>({date:'20300101',races:[{...r,date:'20300101',venue:'seoul',race_no:7}]})});
vm.runInContext('races=[];source={calendar:[{date:"20300101",venues:["seoul"]}]};setVenue("seoul");$("#date").value="2030-01-01";',sandbox);
await vm.runInContext('chooseAvailable()',sandbox);
assert.equal(vm.runInContext('current.race_no',sandbox),7);
assert.equal(nodes['#date'].value,'2030-01-01');
// Pending requests cannot override a newer venue selection.
let resolveFetch;sandbox.fetch=()=>new Promise(resolve=>{resolveFetch=resolve});
vm.runInContext('races=[];$("#date").value="2030-01-01";',sandbox);
const pending=vm.runInContext('chooseAvailable()',sandbox);
vm.runInContext('setVenue("jeju");chooseAvailable()',sandbox);
resolveFetch({ok:true,json:async()=>({date:'20300101',races:[{...r,date:'20300101',venue:'seoul'}]})});await pending;
assert.equal(vm.runInContext('venue',sandbox),'jeju');assert.equal(vm.runInContext('current',sandbox),null);
console.log('PASS lazy historical loading, stale request protection, exact payout hit/miss/refund checks');
console.log('PASS one-click race/date selection, month boundary, region-specific days, automatic valid selection, empty venue');
console.log('PASS: probability normalization, small-field pairs, '+doc.races.length+' live race cards, partial odds ordering, DOM bindings, demo exclusion, duplicate records, separate modes, past/stale recording guards');})().catch(e=>{console.error(e);process.exitCode=1});

