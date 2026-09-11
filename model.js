'use strict';
const clamp=(x,a,b)=>Math.max(a,Math.min(b,x)),div=(a,b,d=0)=>+b?+a/+b:d;
function fieldNorm(v,vals,def=.5){let a=vals.filter(Number.isFinite);if(!Number.isFinite(v)||!a.length)return def;let lo=Math.min(...a),hi=Math.max(...a);return hi>lo?(v-lo)/(hi-lo):def}
function score(h,f){
  let n=+h.starts_1y||0,w=+h.wins_1y||0,s=+h.seconds_1y||0,t=+h.thirds_1y||0;
  // Light Bayesian shrinkage prevents 2-3 starts from looking falsely certain.
  let r3=(w+s+t+1.2)/(n+4),wr=(w+.35)/(n+4);
  let ds=+h.distance_starts||0,dt=+h.distance_top3||0,dr=(dt+.8)/(ds+3);
  let rs=f.map(x=>+x.rating||0),lo=Math.min(...rs),hi=Math.max(...rs),rn=hi>lo?((+h.rating||0)-lo)/(hi-lo):.5;
  let bs=f.map(x=>+x.burden||0).filter(Boolean),ab=bs.reduce((a,b)=>a+b,0)/(bs.length||1),ba=clamp((ab-(+h.burden||0))/5,-1,1);
  let rec=(h.recent_finishes||[]).slice(0,5),weights=rec.map((_,i)=>1-i*.09),rg=rec.length?rec.map((p,i)=>clamp((8-p)/7,0,1)*weights[i]).reduce((a,b)=>a+b,0)/weights.reduce((a,b)=>a+b,0):.35;
  let jp=h.jockey_stats_1y?.place_rate,tp=h.trainer_stats_1y?.place_rate;
  let jn=fieldNorm(jp,f.map(x=>x.jockey_stats_1y?.place_rate)),tn=fieldNorm(tp,f.map(x=>x.trainer_stats_1y?.place_rate));
  let bw=+h.horse_weight||0,bc=h.horse_weight_change==null?null:+h.horse_weight_change;
  let body=0;if(bw>0&&bc!=null){let rel=Math.abs(bc)/bw;body=-clamp((rel-.015)/.045,0,1)}
  let iw=+h.interval_weeks||0,interval=iw?((iw>=2&&iw<=8)?.15:(iw>14?-.35:0)):0;
  let raw=2.10*r3+.55*wr+1.15*dr+.75*rn+.65*rg+.35*jn+.25*tn+.18*ba+.20*body+.10*interval,re=[];
  if(n>=3&&r3>=.42)re.push('최근 전적 안정');
  if(ds>=2&&dr>=.42)re.push('동일거리 강점');
  if(rn>=.72)re.push('레이팅 상위');
  if(rg>=.68)re.push('최근 흐름 양호');
  if(Number.isFinite(jp)&&jp>=.35)re.push('기수 연승률 '+Math.round(jp*100)+'%');
  if(Number.isFinite(tp)&&tp>=.30)re.push('조교사 연승률 '+Math.round(tp*100)+'%');
  if(bw>0&&bc!=null&&Math.abs(bc)>=8)re.push('마체중 '+(bc>0?'+':'')+bc+'kg 주의');
  if(iw>14)re.push('장기 휴양 '+iw+'주');
  if(!re.length)re.push('상대지표 종합');
  let completeness=[n>0,ds>0,rec.length>0,Number.isFinite(jp),Number.isFinite(tp),bw>0].filter(Boolean).length/6;
  return{raw,re,completeness,features:[r3,wr,dr,rn,rg,jn,tn,ba,body,interval]}
}
function probs(st,k){if(st.length<k||k<2) return {p:st.map(()=>0),q:{}};let n=st.length,p=Array(n).fill(0),q={};for(let i=0;i<n;i++)for(let j=i+1;j<n;j++)q[i+'-'+j]=0;let T=st.reduce((a,b)=>a+b,0),add=(o,x)=>{o.forEach(i=>p[i]+=x);for(let a=0;a<o.length;a++)for(let b=a+1;b<o.length;b++){let i=Math.min(o[a],o[b]),j=Math.max(o[a],o[b]);q[i+'-'+j]+=x}};for(let i=0;i<n;i++){let x=st[i]/T,r1=T-st[i];for(let j=0;j<n;j++)if(j!==i){let y=x*st[j]/r1;if(k===2)add([i,j],y);else{let r2=r1-st[j];for(let z=0;z<n;z++)if(z!==i&&z!==j)add([i,j,z],y*st[z]/r2)}}}return{p,q}}

const MODEL_VERSION='4.0';
let learnedModel=null;
function setTrainedModel(report){
 const expected=['place_1y','win_1y','distance_place','relative_rating','recent_form','jockey_place','trainer_place','relative_burden','body_change','interval'];
 learnedModel=report&&report.approved===true&&JSON.stringify(report.features)===JSON.stringify(expected)&&Array.isArray(report.weights)&&report.weights.length===10&&report.weights.every(x=>Number.isFinite(x)&&Math.abs(x)<=6)&&Array.isArray(report.approved_venues)?report:null;
}

function analyze(r,mode='accuracy',odds={place:{},qpl:{}}){
 const h=(r.horses||[]).filter(x=>!x.withdrawn&&!/출전취소|출전제외|경주취소/.test(x.note||'')).map(x=>({...x}));
 if(h.length<3||h.length>20||new Set(h.map(x=>+x.number)).size!==h.length||h.some(x=>!Number.isInteger(+x.number)||+x.number<1))throw Error('서로 다른 출전마 3~20두가 필요합니다.');
 const trained=learnedModel&&learnedModel.approved_venues.includes(r.venue);
 const sc=h.map(x=>score(x,h)),raw=sc.map(x=>trained?x.features.reduce((a,v,i)=>a+v*learnedModel.weights[i],0)/.6:x.raw),mean=raw.reduce((a,b)=>a+b,0)/h.length;
 const st=raw.map(x=>Math.exp(clamp((x-mean)*.6,-4,4))),k=h.length<=7?2:3,place=probs(st,k),pair=probs(st,3);
 h.forEach((x,i)=>{x.prob=place.p[i];x.reasons=sc[i].re;x.quality=sc[i].completeness;});
 const item=(numbers,p,quality,market)=>{const key=numbers.join('-'),odd=Number(market[key]??market[[...numbers].reverse().join('-')]);return {numbers,prob:p,quality,odds:Number.isFinite(odd)&&odd>=1?odd:null,ev:Number.isFinite(odd)&&odd>=1?p*odd-1:null};};
 const places=h.map(x=>({...item([x.number],x.prob,x.quality,odds.place||{}),names:[x.name]}));
 const pairs=[];for(let i=0;i<h.length;i++)for(let j=i+1;j<h.length;j++)pairs.push({...item([h[i].number,h[j].number],pair.q[i+'-'+j],Math.min(h[i].quality,h[j].quality),odds.qpl||{}),names:[h[i].name,h[j].name]});
 const compare=mode==='value'?(a,b)=>(b.ev??-Infinity)-(a.ev??-Infinity)||b.prob-a.prob:(a,b)=>b.prob-a.prob;
 places.sort(compare);pairs.sort(compare);
 const sparse=h.filter(x=>(+x.starts_1y||0)<3).length/h.length;
 const reasons=[];if(sparse>=.3)reasons.push('전적 3회 미만 출전마가 30% 이상');
 if(h.filter(x=>x.quality<.5).length/h.length>=.3)reasons.push('출전마 정보 부족');
 return {...r,horses:h.sort((a,b)=>b.prob-a.prob),places,pairs,k,mode,reasons,model:trained?learnedModel.model:MODEL_VERSION};
}
function candidateReasons(r,x,type){
 const why=[...r.reasons];if(!x)return ['후보 없음'];if(x.quality<2/3)why.push('후보 데이터 부족');
 if(r.mode==='value'&&(x.ev===null||x.ev<(type==='place'?.1:.15)))why.push(x.ev===null?'배당 입력 필요':'검토 기준 미달');
 return why;
}
if(typeof module!=='undefined')module.exports={analyze,probs,candidateReasons,MODEL_VERSION,setTrainedModel};

