'use strict';
const challengerEngine=typeof module!=='undefined'?require('./model-v7.js'):globalThis.KraV7;
function setChallengerModel(r){return challengerEngine?.configure(r)||false;}
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
let advancedModel=null;
const ADVANCED_FEATURES=['place_1y','win_1y','distance_place','relative_rating','recent_form','jockey_place','trainer_place','relative_burden','days_since_run','history_count','finish_fraction','form_trend','finish_consistency','distance_change','burden_change','recent_margin','relative_speed','opponent_rating','jockey_horse','distance_experience','field_size','place_slots','distance','seoul','busan','jeju','sparse_field','speed_available','margin_available','relative_recent_form','rating_level','long_break'];
const PAIR_COLUMNS=[...Array.from({length:20},(_,i)=>i),27,28,29,30,31];
function validEstimator(m,width){
 if(!m||!Number.isFinite(m.bias))return false;
 if(m.kind==='linear')return Array.isArray(m.weights)&&m.weights.length===width&&m.weights.every(Number.isFinite);
 return m.kind==='tree'&&Array.isArray(m.trees)&&m.trees.length>0&&m.trees.length<=200&&m.trees.every(t=>Array.isArray(t)&&t.length>0&&t.length<=63&&t.every((n,i)=>Array.isArray(n)&&n.length===6&&n.every(Number.isFinite)&&(n[0]===1||(n[0]===0&&Number.isInteger(n[1])&&n[1]>=0&&n[1]<width&&[n[3],n[4]].every(c=>Number.isInteger(c)&&c>i&&c<t.length)))));
}
function setAdvancedModel(r){
 advancedModel=null;
 if(!r||r.schema!==2||r.feature_version!=='6.0-conditions'||JSON.stringify(r.features)!==JSON.stringify(ADVANCED_FEATURES)||JSON.stringify(r.pair_columns)!==JSON.stringify(PAIR_COLUMNS))return false;
 for(const kind of ['place','pair']){
  if(typeof r.deployment?.[kind]?.approved!=='boolean'||typeof r.policies?.[kind]?.approved!=='boolean')return false;
  if(!validEstimator(r.models?.[kind],kind==='place'?32:82))return false;
  const c=r.calibrators?.[kind],p=r.policies?.[kind];
  if(!c||!Number.isFinite(c.a)||c.a<=0||!Number.isFinite(c.b)||!p||!Array.isArray(p.approved_venues))return false;
  if(p.approved&&(!p.criteria||!['min_probability','min_gap','min_starts','max_sparse'].every(k=>Number.isFinite(p.criteria[k]))))return false;
 }
 advancedModel=r;return true;
}
function predictEstimator(m,x){
 let z=m.bias;
 if(m.kind==='linear')z+=m.weights.reduce((a,w,i)=>a+w*x[i],0);
 else for(const t of m.trees){let i=0;while(!t[i][0])i=x[t[i][1]]<=t[i][2]?t[i][3]:t[i][4];z+=t[i][5]}
 return 1/(1+Math.exp(-z));
}
function pairFeatures(a,b){return [...PAIR_COLUMNS.map(i=>(a[i]+b[i])/2),...PAIR_COLUMNS.map(i=>Math.min(a[i],b[i])),...PAIR_COLUMNS.map(i=>Math.abs(a[i]-b[i])),...a.slice(20,27)]}
function calibrated(m,x,kind){const p=clamp(predictEstimator(m.models[kind],x),1e-6,1-1e-6),c=m.calibrators[kind];return 1/(1+Math.exp(-(c.a*Math.log(p/(1-p))+c.b)))}
function advancedReady(r,h){
 if(!advancedModel||r.feature_version!==advancedModel.feature_version||!/^\d{8}$/.test(r.history_through||'')||r.history_through>=r.date)return false;
 const parse=d=>Date.parse(d.slice(0,4)+'-'+d.slice(4,6)+'-'+d.slice(6,8)+'T00:00:00Z');
 if(!Number.isFinite(parse(r.date))||parse(r.date)-parse(r.history_through)>7*86400000)return false;
 return h.every(x=>Array.isArray(x.features_v6)&&x.features_v6.length===32&&x.features_v6.every(v=>Number.isFinite(v)&&Math.abs(v)<=20)&&Math.abs(x.features_v6[20]-h.length/20)<1e-8&&Math.abs(x.features_v6[21]-(h.length<=7?2:3)/3)<1e-8&&Math.abs(x.features_v6[22]-r.distance/2500)<1e-8&&x.quality_v6&&Number.isFinite(x.quality_v6.starts)&&Number.isFinite(x.quality_v6.sparse));
}
function selectiveStatus(r,items,type,active){
 const policy=advancedModel?.policies[type],x=items[0];
 const status={qualified:false,available:false,reason:'선별 기준 검증 대기'};
 if(!active)return advancedModel?.deployment?.[type]?.approved?{...status,reason:'과거 기록 갱신 대기 · 일반 후보 제공'}:status;
 if(!policy?.approved)return status;
 if(!policy.approved_venues.includes(r.venue))return {...status,reason:'이 지역은 선별 검증 표본 부족 또는 기준 미달'};
 status.available=true;
 if(r.mode==='value')return {...status,reason:'적중률 우선 기준에서 선별 표시'};
 const p=policy.criteria,qs=x.numbers.map(n=>r.horses.find(h=>h.number===n).quality_v6);
 status.qualified=x.prob>=p.min_probability&&x.prob-(items[1]?.prob||0)>=p.min_gap&&Math.min(...qs.map(q=>q.starts))>=p.min_starts&&Math.max(...qs.map(q=>q.sparse))<=p.max_sparse;
 status.reason=status.qualified?'과거 검증을 통과한 선별 기준 충족':'일반 후보 · 선별 기준 미충족';
 return status;
}
function setTrainedModel(report){
 const expected=['place_1y','win_1y','distance_place','relative_rating','recent_form','jockey_place','trainer_place','relative_burden','body_change','interval'];
 learnedModel=report&&report.approved===true&&JSON.stringify(report.features)===JSON.stringify(expected)&&Array.isArray(report.weights)&&report.weights.length===10&&report.weights.every(x=>Number.isFinite(x)&&Math.abs(x)<=6)&&Array.isArray(report.approved_venues)?report:null;
}

function analyze(r,mode='accuracy',odds={place:{},qpl:{}}){
 const h=(r.horses||[]).filter(x=>!x.withdrawn&&!/출전취소|출전제외|경주취소/.test(x.note||'')).map(x=>({...x})).sort((a,b)=>+a.number-+b.number);
 if(h.length<3||h.length>20||new Set(h.map(x=>+x.number)).size!==h.length||h.some(x=>!Number.isInteger(+x.number)||+x.number<1))throw Error('서로 다른 출전마 3~20두가 필요합니다.');
 const trained=learnedModel&&learnedModel.approved_venues.includes(r.venue);
 const sc=h.map(x=>score(x,h)),raw=sc.map(x=>trained?x.features.reduce((a,v,i)=>a+v*learnedModel.weights[i],0)/.6:x.raw),mean=raw.reduce((a,b)=>a+b,0)/h.length;
 const st=raw.map(x=>Math.exp(clamp((x-mean)*.6,-4,4))),k=h.length<=7?2:3,place=probs(st,k),pair=probs(st,3);
 const ready=advancedReady(r,h),active={place:!!(ready&&advancedModel.deployment?.place?.approved),pair:!!(ready&&advancedModel.deployment?.pair?.approved)};
 const selectiveActive={place:!!(ready&&advancedModel.policies.place.approved),pair:!!(ready&&advancedModel.policies.pair.approved)};
 const vp=(active.place||selectiveActive.place)?h.map(x=>calibrated(advancedModel,x.features_v6,'place')):null,vq={};
 if(active.pair||selectiveActive.pair)for(let i=0;i<h.length;i++)for(let j=i+1;j<h.length;j++)vq[i+'-'+j]=calibrated(advancedModel,pairFeatures(h[i].features_v6,h[j].features_v6),'pair');
 if(active.place)h.forEach((x,i)=>place.p[i]=vp[i]);
 if(active.pair)Object.assign(pair.q,vq);
 h.forEach((x,i)=>{x.prob=place.p[i];x.reasons=sc[i].re;x.quality=sc[i].completeness;});
 const item=(numbers,p,quality,market)=>{const key=numbers.join('-'),odd=Number(market[key]??market[[...numbers].reverse().join('-')]);return {numbers,prob:p,quality,odds:Number.isFinite(odd)&&odd>=1?odd:null,ev:Number.isFinite(odd)&&odd>=1?p*odd-1:null};};
 const places=h.map(x=>({...item([x.number],x.prob,x.quality,odds.place||{}),names:[x.name]}));
 const pairs=[];for(let i=0;i<h.length;i++)for(let j=i+1;j<h.length;j++)pairs.push({...item([h[i].number,h[j].number],pair.q[i+'-'+j],Math.min(h[i].quality,h[j].quality),odds.qpl||{}),names:[h[i].name,h[j].name]});
 const selectivePlaces=vp?h.map((x,i)=>({...item([x.number],vp[i],x.quality,{}),names:[x.name]})).sort((a,b)=>b.prob-a.prob):[];
 const selectivePairs=[];if(selectiveActive.pair)for(let i=0;i<h.length;i++)for(let j=i+1;j<h.length;j++)selectivePairs.push({...item([h[i].number,h[j].number],vq[i+'-'+j],Math.min(h[i].quality,h[j].quality),{}),names:[h[i].name,h[j].name]});
 selectivePairs.sort((a,b)=>b.prob-a.prob);
 const compare=mode==='value'?(a,b)=>(b.ev??-Infinity)-(a.ev??-Infinity)||b.prob-a.prob:(a,b)=>b.prob-a.prob;
 places.sort(compare);pairs.sort(compare);
 const sparse=h.filter(x=>(+x.starts_1y||0)<3).length/h.length;
 const reasons=[];if(sparse>=.3)reasons.push('전적 3회 미만 출전마가 30% 이상');
 if(h.filter(x=>x.quality<.5).length/h.length>=.3)reasons.push('출전마 정보 부족');
 const result={...r,horses:h.sort((a,b)=>b.prob-a.prob),places,pairs,k,mode,reasons,advanced:active,model:active.place||active.pair?advancedModel.model:(trained?learnedModel.model:MODEL_VERSION)};
 result.models={place:active.place?advancedModel.model:(trained?learnedModel.model:MODEL_VERSION),pair:active.pair?advancedModel.model:(trained?learnedModel.model:MODEL_VERSION)};
 result.selectiveActive=selectiveActive;
 result.selection={place:selectiveStatus(result,selectivePlaces,'place',selectiveActive.place),pair:selectiveStatus(result,selectivePairs,'pair',selectiveActive.pair)};
 result.selectivePicks={place:result.selection.place.qualified?selectivePlaces[0]:null,pair:result.selection.pair.qualified?selectivePairs[0]:null};
 result.incumbent={model:{...result.models},place:result.places.slice(),pair:result.pairs.slice()};
 const challenger=challengerEngine?.analyze(r);result.challenger=challenger;
 if(challenger)for(const type of ['place','pair'])if(challenger.deployment[type].approved){
  const market=type==='place'?odds.place:odds.qpl;
  const items=challenger[type].map(x=>({...x,...item(x.numbers,x.prob,1,market||{})})).sort(compare);
  result[type==='place'?'places':'pairs']=items;result.models[type]=challenger.model;result.advanced[type]=true;
  if(type==='place')result.horses.forEach(h=>h.prob=items.find(x=>x.numbers[0]===h.number).prob);
  result.model=challenger.model;
 }
 return result;
}
function candidateReasons(r,x,type){
 const why=r.advanced?.[type]?[]:[...r.reasons];if(!x)return ['후보 없음'];if(!r.advanced?.[type]&&x.quality<2/3)why.push('후보 데이터 부족');
 if(r.mode==='value'&&(x.ev===null||x.ev<(type==='place'?.1:.15)))why.push(x.ev===null?'배당 입력 필요':'검토 기준 미달');
 return why;
}
if(typeof module!=='undefined')module.exports={setChallengerModel,analyze,probs,candidateReasons,MODEL_VERSION,setTrainedModel,setAdvancedModel,predictEstimator,pairFeatures,advancedReady};
