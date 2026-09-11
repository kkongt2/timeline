const assert=require('node:assert/strict'),fs=require('fs'),os=require('os'),path=require('path');
const {run,settle}=require('../scripts/snapshot.cjs');
const root=fs.mkdtempSync(path.join(os.tmpdir(),'kra-snapshot-')),data=path.join(root,'data');fs.mkdirSync(data);
for(const name of ['model.js','model-v7.js'])fs.copyFileSync(path.join(__dirname,'..',name),path.join(root,name));
const now=new Date('2026-09-12T02:00:00Z');
const card={date:'20260912',venue:'seoul',race_no:1,distance:1200,start_time:'12:00',horses:[1,2,3,4].map(n=>({number:n,name:'말'+n,age:3,sex:'수',rating:50-n,burden:55,starts_1y:10,wins_1y:1,seconds_1y:2,thirds_1y:2}))};
function doc(r=card,updated_at=now.toISOString()){fs.writeFileSync(path.join(data,'latest.json'),JSON.stringify({updated_at,races:[r]}));}
try{
 doc();let s=run(root,now);assert.equal(s.recorded_races,1);
 const archive=path.join(data,'predictions','20260912.json'),saved=fs.readFileSync(archive,'utf8');
 const record=Object.values(JSON.parse(saved).races)[0];assert(!record.input.official_result);assert.equal(record.tracks.general.pair.length,6);
 card.horses[0].rating=1;doc();run(root,new Date(now.getTime()+5*60000));assert.equal(fs.readFileSync(archive,'utf8'),saved);
 const p=record.tracks.general.place[0],q=record.tracks.general.pair[0];
 card.official_result={status:'confirmed',starters:[1,2,3,4],place:{status:'confirmed',payouts:[{numbers:p.numbers,odds:1.8}]},pair:{status:'confirmed',payouts:[{numbers:q.numbers,odds:3.2}]}};
 doc();s=run(root,new Date('2026-09-12T04:00:00Z'));assert.equal(s.groups.find(g=>g.kind==='place').hits,1);assert.equal(s.groups.find(g=>g.kind==='pair').hits,1);assert.equal(fs.readFileSync(archive,'utf8'),saved);
 const clone={...card,race_no:2,official_result:undefined};doc(clone);assert.equal(run(root,new Date('2026-09-12T04:00:00Z')).recorded_races,1);
 doc(clone,'2000-01-01T00:00:00Z');assert.equal(run(root,now).recorded_races,1);
 doc({...clone,start_time:'11:10'});assert.equal(run(root,now).recorded_races,1);
 assert.equal(settle({numbers:[5],prob:.4},card.official_result,'place').status,'void');
 assert.equal(settle(p,{...card.official_result,starters:null},'place').status,'pending');
 assert.equal(settle(p,{place:{status:'refunded'}},'place').status,'void');
 console.log('PASS immutable first forecast, source freshness and time window, no backfill, official settlement, withdrawal/refund exclusion');
}finally{fs.rmSync(root,{recursive:true,force:true});}
