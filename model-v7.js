'use strict';
(function(root){
 let report=null;
 const features=["place_1y","win_1y","distance_place","relative_rating","recent_form","jockey_place","trainer_place","relative_burden","days_since_run","history_count","finish_fraction","form_trend","finish_consistency","distance_change","burden_change","recent_margin","relative_speed","opponent_rating","jockey_horse","distance_experience","field_size","place_slots","distance","seoul","busan","jeju","sparse_field","speed_available","margin_available","relative_recent_form","rating_level","long_break","actual_place_1y","actual_distance_place","actual_jockey_place","actual_trainer_place","near_distance_form","rating_change","grade_change","opponent_adjusted_margin","early_strength","finish_gain","leader_rate","relative_early_speed","relative_last_speed","sectional_coverage","position_coverage","field_leader_fraction","stronger_rivals","near_distance_experience","age","identity_history_available"];
 const columns=[...Array.from({length:20},(_,i)=>i),27,28,29,30,31,...Array.from({length:15},(_,i)=>i+32),48,49,50,51];
 const width=columns.length*3+17;
 function configure(r){
  report=null;
  if(!r||r.schema!==3||r.feature_version!=='7.0-race-pace'||JSON.stringify(r.features)!==JSON.stringify(features)||JSON.stringify(r.pair_columns)!==JSON.stringify(columns))return false;
  for(const k of ['place','pair']){
   const m=r.models?.[k],c=r.calibrators?.[k];
   if(!m||!Number.isFinite(m.bias)||m.kind!=='tree'||!Array.isArray(m.trees)||!m.trees.length||m.trees.length>200||!m.trees.every(t=>Array.isArray(t)&&t.length&&t.length<=63&&t.every((n,i)=>Array.isArray(n)&&n.length===6&&n.every(Number.isFinite)&&(n[0]===1||(n[0]===0&&Number.isInteger(n[1])&&n[1]>=0&&n[1]<(k==='place'?52:width)&&[n[3],n[4]].every(j=>Number.isInteger(j)&&j>i&&j<t.length))))))return false;
   if(!c||!Number.isFinite(c.a)||c.a<=0||!Number.isFinite(c.b)||!['core','pace'].includes(r.feature_modes?.[k])||typeof r.deployment?.[k]?.approved!=='boolean')return false;
  }
  report=r;return true;
 }
 const mean=a=>a.reduce((s,v)=>s+v,0)/(a.length||1),max=a=>a.length?Math.max(...a):0;
 function pairFeatures(a,b,others){
  return [...columns.map(i=>(a[i]+b[i])/2),...columns.map(i=>Math.min(a[i],b[i])),...columns.map(i=>Math.abs(a[i]-b[i])),...a.slice(20,27),
   max(others.map(x=>x[30])),mean(others.map(x=>x[30])),mean(others.map(x=>+(x[30]>Math.min(a[30],b[30])))),
   max(others.map(x=>x[4])),max(others.map(x=>x[32])),mean(others.map(x=>x[42])),a[42]*b[42],Math.abs(a[43]-b[43]),Math.min(a[41],b[41]),mean(others.map(x=>+(x[42]>.5&&x[46]>0)))];
 }
 function prepared(x,mode){const a=x.slice();if(mode==='core')for(let i=40;i<=47;i++)a[i]=0;return a;}
 function predict(m,x,c){let z=m.bias;for(const tree of m.trees){let i=0;while(!tree[i][0])i=x[tree[i][1]]<=tree[i][2]?tree[i][3]:tree[i][4];z+=tree[i][5];}const p=Math.max(1e-6,Math.min(1-1e-6,1/(1+Math.exp(-z))));return 1/(1+Math.exp(-(c.a*Math.log(p/(1-p))+c.b)));}
 function analyze(r){
  const h=(r.horses||[]).filter(x=>!x.withdrawn&&!/출전취소|출전제외|경주취소/.test(x.note||'')).slice().sort((a,b)=>a.number-b.number);
  const d=s=>Date.parse(String(s).replace(/^(\d{4})(\d{2})(\d{2})$/,'$1-$2-$3')+'T00:00:00Z');
  if(!report||r.feature_version_v7!==report.feature_version||!/^\d{8}$/.test(r.history_through_v7||'')||!(d(r.date)>d(r.history_through_v7))||d(r.date)-d(r.history_through_v7)>7*86400000||!h.length||!h.every(x=>Array.isArray(x.features_v7)&&x.features_v7.length===52&&x.features_v7.every(v=>Number.isFinite(v)&&Math.abs(v)<=20)&&Math.abs(x.features_v7[20]-h.length/20)<1e-8&&Math.abs(x.features_v7[22]-r.distance/2500)<1e-8&&Math.abs(x.features_v7[21]-(h.length<=7?2:3)/3)<1e-8))return null;
  const out={model:report.model,place:[],pair:[],deployment:report.deployment};
  for(const kind of ['place','pair']){
   const X=h.map(x=>prepared(x.features_v7,report.feature_modes[kind]));
   const add=(ix,x)=>out[kind].push({numbers:ix.map(i=>h[i].number),names:ix.map(i=>h[i].name),prob:predict(report.models[kind],x,report.calibrators[kind])});
   if(kind==='place')X.forEach((x,i)=>add([i],x));
   else for(let i=0;i<h.length;i++)for(let j=i+1;j<h.length;j++)add([i,j],pairFeatures(X[i],X[j],X.filter((_,k)=>k!==i&&k!==j)));
   out[kind].sort((a,b)=>b.prob-a.prob);
  }
  return out;
 }
 root.KraV7={configure,analyze,pairFeatures,prepared,predict,width};
 if(typeof module!=='undefined')module.exports=root.KraV7;
})(typeof globalThis!=='undefined'?globalThis:this);
