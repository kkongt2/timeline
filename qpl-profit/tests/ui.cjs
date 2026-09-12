const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
class Element{constructor(){this.children=[];this.handlers={};this.innerHTML='';this.textContent='';this.attributes={};}replaceChildren(...children){this.children=children;}addEventListener(event,fn){this.handlers[event]=fn;}setAttribute(k,v){this.attributes[k]=v;}click(){this.handlers.click?.();}}
const els=new Map(),get=id=>{if(!els.has(id))els.set(id,new Element());return els.get(id);};
const RealDate=Date;class FixedDate extends RealDate{constructor(...a){super(...(a.length?a:['2026-09-12T00:20:00Z']));}static now(){return +new RealDate('2026-09-12T00:20:00Z');}}
const context=vm.createContext({document:{getElementById:get,createElement:()=>new Element()},Date:FixedDate,Intl,console,setInterval:()=>{},QPL:require('../model.js'),fetch:async path=>({ok:true,json:async()=>JSON.parse(fs.readFileSync(path.split('?')[0]==='data/latest.json'?'tests/ui-fixture.json':path.split('?')[0],'utf8'))})});
vm.runInContext(fs.readFileSync('app.js','utf8'),context);
setImmediate(()=>{
  assert.match(get('race-content').innerHTML,/손익분기 배당/);assert.match(get('race-content').innerHTML,/나머지/);assert.match(get('race-content').innerHTML,/베팅 추천을 보류/);
  const next=get('rounds').children[1];assert.ok(next);next.click();assert.equal(vm.runInContext('state.round',context),2);assert.match(get('race-content').innerHTML,/2경주/);
  get('venues').children.find(b=>b.textContent==='제주').click();
  const dates=vm.runInContext("[...new Set(state.doc.races.filter(r=>r.venue==='jeju').map(r=>r.date))].sort()",context);
  assert.equal(get('dates').children.length,dates.length);
  get('dates').children[0].click();assert.match(get('race-content').innerHTML,/복연승 실제 결과/);assert.match(get('race-content').innerHTML,/1\.5배/);assert.doesNotMatch(get('race-content').innerHTML,/추정 적중확률/);
  assert.match(get('metrics').innerHTML,/26,100원/);assert.match(get('validation').innerHTML,/최고 수익일/);
  console.log('PASS one-click round, region-specific dates, all combination break-even dividends, official past outcomes, abstention and profit metrics');
});
