// First eligible forecast per race is immutable. Outcomes live in separate files.
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const engine=require('../model.js');
const hash=x=>crypto.createHash('sha256').update(typeof x==='string'?x:JSON.stringify(x)).digest('hex');
const read=(p,def=null)=>fs.existsSync(p)?JSON.parse(fs.readFileSync(p,'utf8')):def;
function write(p,x){fs.mkdirSync(path.dirname(p),{recursive:true});const s=JSON.stringify(x,null,2)+'\n';if(fs.existsSync(p)&&fs.readFileSync(p,'utf8')===s)return;fs.writeFileSync(p+'.tmp',s);fs.renameSync(p+'.tmp',p);}
const start=r=>Date.parse(String(r.date).replace(/^(\d{4})(\d{2})(\d{2})$/,'$1-$2-$3')+'T'+r.start_time+':00+09:00');
const key=r=>[r.date,r.venue,r.race_no].join(':');
const normalize=a=>a.slice().sort((a,b)=>a-b).join('-');
function settle(pick,result,kind){
 const market=result?.[kind];
 if(market?.status==='refunded')return {status:'void'};
 if(market?.status!=='confirmed'||!Array.isArray(result.starters))return {status:'pending'};
 if(pick.numbers.some(n=>!result.starters.includes(n)))return {status:'void'};
 const payout=market.payouts.find(p=>normalize(p.numbers)===normalize(pick.numbers));
 return {status:'settled',hit:!!payout,odds:payout?.odds||0,prob:pick.prob};
}
function run(root=path.resolve(__dirname,'..'),now=new Date()){
 const data=path.join(root,'data'),doc=read(path.join(data,'latest.json'),{races:[]});
 const legacy=read(path.join(data,'training-report.json')),advanced=read(path.join(data,'model-v6.json')),candidate=read(path.join(data,'model-v7.json'));
 engine.setTrainedModel(legacy);engine.setAdvancedModel(advanced);engine.setChallengerModel(candidate);
 const bundles={general:hash([legacy,advanced,candidate]),challenger:hash(candidate),selective:hash(advanced)};
 const codeHash=hash(fs.readFileSync(path.join(root,'model.js'),'utf8')+fs.readFileSync(path.join(root,'model-v7.js'),'utf8'));
 const archives=new Map(),dir=path.join(data,'predictions');fs.mkdirSync(dir,{recursive:true});
 for(const file of fs.readdirSync(dir).filter(x=>/^\d{8}\.json$/.test(x))){const a=read(path.join(dir,file));if(a.schema!==1)throw Error('Unknown forecast archive');archives.set(file.slice(0,8),a);}
 let added=0;
 for(const r of doc.races){
  const minutes=(start(r)-now.getTime())/60000,age=now.getTime()-Date.parse(doc.updated_at);
  if(!Number.isFinite(minutes)||minutes<15||minutes>90||!Number.isFinite(age)||age<0||age>30*60000||r.official_result?.status==='confirmed')continue;
  const a=archives.get(r.date)||{schema:1,date:r.date,races:{}};if(a.races[key(r)])continue;
  const input=JSON.parse(JSON.stringify(r));delete input.official_result;
  if(input.horses.some(h=>h.finish!=null||h.finish_status!=null))continue;
  const result=engine.analyze(input,'accuracy'),tracks={};
  const copy=x=>({numbers:x.numbers,prob:x.prob});
  tracks.general={model:result.models,bundle_hash:bundles.general,place:result.places.map(copy),pair:result.pairs.map(copy)};
  if(result.incumbent&&Object.values(result.models).some(v=>v!==result.incumbent.model.place))tracks.incumbent={model:result.incumbent.model,bundle_hash:hash([legacy,advanced]),place:result.incumbent.place.map(copy),pair:result.incumbent.pair.map(copy)};
  if(result.challenger)tracks.challenger={model:{place:result.challenger.model,pair:result.challenger.model},bundle_hash:bundles.challenger,place:result.challenger.place.map(copy),pair:result.challenger.pair.map(copy)};
  const selected={};for(const k of ['place','pair'])if(result.selectivePicks[k])selected[k]=[copy(result.selectivePicks[k])];
  if(Object.keys(selected).length)tracks.selective={model:{place:advanced.model,pair:advanced.model},bundle_hash:bundles.selective,...selected};
  a.races[key(r)]={id:key(r),saved_at:now.toISOString(),source_updated_at:doc.updated_at,start_at:new Date(start(r)).toISOString(),input_hash:hash(input),code_hash:codeHash,input,tracks};
  archives.set(r.date,a);added++;
 }
 for(const [date,a] of archives)write(path.join(dir,date+'.json'),a);
 const settledDir=path.join(data,'settlements');fs.mkdirSync(settledDir,{recursive:true});
 const outcomes={};for(const file of fs.readdirSync(settledDir).filter(x=>/^\d{8}\.json$/.test(x)))Object.assign(outcomes,read(path.join(settledDir,file),{}));
 const freshByDate={};for(const r of doc.races)if(r.official_result){(freshByDate[r.date]??={})[key(r)]=r.official_result;outcomes[key(r)]=r.official_result;}
 for(const [date,items] of Object.entries(freshByDate))write(path.join(settledDir,date+'.json'),{...read(path.join(settledDir,date+'.json'),{}),...items});
 const groups={},paired={},recent=[];
 for(const a of archives.values())for(const r of Object.values(a.races)){
  const row={id:r.id,date:r.input.date,venue:r.input.venue,race_no:r.input.race_no,saved_at:r.saved_at,tracks:{}};
  for(const [track,t] of Object.entries(r.tracks)){
   row.tracks[track]={};
   for(const kind of ['place','pair']){
    if(!t[kind]?.length)continue;
    const id=[track,t.bundle_hash,r.code_hash,kind].join(':');
    const g=groups[id]??={id,track,kind,model:t.model[kind],bundle_hash:t.bundle_hash,recorded:0,settled:0,hits:0,pending:0,void:0,brier_sum:0};g.recorded++;
    const outcome=settle(t[kind][0],outcomes[r.id],kind);
    row.tracks[track][kind]={...t[kind][0],...outcome};
    if(outcome.status==='settled'){g.settled++;g.hits+=+outcome.hit;g.brier_sum+=(outcome.prob-Number(outcome.hit))**2;}
    else g[outcome.status]++;
   }
  }
  const baseline=row.tracks.incumbent||row.tracks.general;
  if(row.tracks.challenger)for(const kind of ['place','pair']){
   const a=baseline?.[kind],b=row.tracks.challenger[kind];
   if(a?.status!=='settled'||b?.status!=='settled')continue;
   const bt=r.tracks.incumbent||r.tracks.general,ct=r.tracks.challenger,id=[kind,bt.bundle_hash,ct.bundle_hash,r.code_hash].join(':');
   const p=paired[id]??={id,kind,baseline_model:bt.model[kind],challenger_model:ct.model[kind],races:0,baseline_hits:0,challenger_hits:0};
   p.races++;p.baseline_hits+=Number(a.hit);p.challenger_hits+=Number(b.hit);
  }
  recent.push(row);
 }
 const summary={schema:1,updated_at:now.toISOString(),window:{min_minutes:15,max_minutes:90},recorded_races:recent.length,
  paired:Object.values(paired),
  groups:Object.values(groups).map(g=>({...g,hit_rate:g.settled?g.hits/g.settled:null,brier:g.settled?g.brier_sum/g.settled:null})),
  recent:recent.sort((a,b)=>b.saved_at.localeCompare(a.saved_at)).slice(0,100)};
 write(path.join(data,'prediction-summary.json'),summary);
 console.log(JSON.stringify({added,recorded_races:recent.length,groups:summary.groups.length}));return summary;
}
if(require.main===module)run();module.exports={run,settle,start,key};
