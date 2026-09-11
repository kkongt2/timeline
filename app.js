'use strict';
const $=s=>document.querySelector(s),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct=x=>(x*100).toFixed(1)+'%',names={seoul:'서울',busan:'부경',jeju:'제주'},KEY='kra-predictions-v4';
let races=[],source=null,current=null,ranked=null,venue='seoul',odds={place:{},qpl:{}},manual=false,requestId=0,advancedReport=null;
const day=()=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
function breakEvenOdds(p){const odds=1/p;return Number.isFinite(p)&&p>0&&p<=1+1e-9&&Number.isFinite(odds)?Math.max(1,odds).toFixed(2):null;}
function probabilityHTML(p){const odds=breakEvenOdds(p);return '<span class="probability-values"><span class="probability-rate">'+(odds?pct(p):'—')+'</span><span class="break-even">손익분기배당 '+(odds?'약 '+odds+'배':'—')+'</span></span>';}
function start(r){const d=String(r.date||'').replaceAll('-','');return /^\d{8}$/.test(d)&&/^\d{2}:\d{2}$/.test(r.start_time||'')?Date.parse(`${d.slice(0,4)}-${d.slice(4,6)}-${d.slice(6,8)}T${r.start_time}:00+09:00`):NaN;}
function setVenue(v){venue=v;document.querySelectorAll('[data-venue]').forEach(b=>{b.classList.toggle('active',b.dataset.venue===v);b.setAttribute('aria-pressed',b.dataset.venue===v)});}
function records(){try{let a=JSON.parse(localStorage.getItem(KEY)||'[]');return Array.isArray(a)?a:[]}catch{return []}}
function put(a){try{localStorage.setItem(KEY,JSON.stringify(a));return true}catch{$('#saveStatus').textContent='기기에 저장하지 못했습니다. 브라우저 저장 공간을 확인하세요.';return false}}
function timingReasons(r){const why=[];if(!Number.isFinite(start(r)))why.push('출발 시각 확인 필요');else if(start(r)<=Date.now())why.push(String(r.date)<day().replaceAll('-','')?'지난 경주 조회 · 현재 정보로 재계산한 후보':'이미 출발한 경주');if(!manual&&(!source?.updated_at||Date.now()-Date.parse(source.updated_at)>30*60000||!Number.isFinite(Date.parse(source.updated_at))))why.push('갱신 후 30분 경과 · 최신 출전정보 확인 필요');return why;}
function why(r,x,type){return [...candidateReasons(r,x,type),...timingReasons(r),...(manual?['직접 입력 / 데모']:[])];}
function isSelected(r,type){return !manual&&r.mode==='accuracy'&&r.selection?.[type]?.qualified===true&&timingReasons(r).length===0;}
function officialResultHTML(r,type){
 if(!Number.isFinite(start(r))||start(r)>Date.now())return '';
 const result=r.official_result,market=result?.[type];
 const title='<span class="result-label">실제 결과 · 확정 배당</span>';
 if(market?.status==='confirmed'&&market.payouts?.length){
  return '<span class="official-result">'+title+market.payouts.map(x=>'<span class="result-line"><strong>'+x.numbers.map(n=>esc(n)).join('–')+(type==='place'?'번':'')+'</strong><span>'+Number(x.odds).toFixed(1)+'배</span></span>').join('')+'</span>';
 }
 return '<span class="official-result">'+title+'<span class="result-pending">'+(market?.status==='refunded'?'환불':result?.status==='unavailable'?'결과 불러오기 대기':'공식 결과 확인 중')+'</span></span>';
}
function pickHTML(x,r,type,lead=false){
 if(!x)return '<p class="hint">후보 없음</p>';
 const reasons=why(r,x,type),name=x.names.map(esc).join(' · '),num=x.numbers.join(' – '),selected=false;
 if(!lead)return `<div class="candidate"><span><b>${num}</b> ${name}${x.odds?`<br>${x.odds}배 · 추정 EV ${pct(x.ev)}`:''}</span><span class="candidate-metrics"><span class="candidate-probability-label">추정확률</span>${probabilityHTML(x.prob)}</span></div>`;
 const status=selected?'선별 후보':reasons.length?'확인 필요 · 후보 제공':'일반 후보';
 const explanation=reasons.length?reasons.join(' · '):'전체 경주용 모델의 1순위 후보';
 const pick=isSelected(r,type)?r.selectivePicks[type]:null;
 const selectionHTML=pick?'<div class="selective-pick"><span class="selected-tag">선별용 모델 후보</span><strong>'+pick.numbers.join(' – ')+'</strong><span>'+pick.names.map(esc).join(' · ')+'</span><small>추정 '+probabilityHTML(pick.prob)+'</small><small>검증 기준 충족</small></div>':'<p class="hint">'+esc(r.selection?.[type]?.reason||'선별 검증 대기')+'</p>';
 return `<div class="status ${selected?'selected':reasons.length?'hold':''}">${status}</div><div class="lead-number">${num}</div><p class="lead-name">${name}</p><div class="prob"><small>추정 ${type==='place'?'입상':'동반입상'}</small>${probabilityHTML(x.prob)}</div><p class="hint">${esc(explanation)}</p>${selectionHTML}${manual?'':officialResultHTML(r,type)}${x.odds?`<p class="hint">${x.odds}배 · 추정 EV ${pct(x.ev)}</p>`:''}`;
}
function render(){if(!current)return;ranked=analyze(current,$('#mode').value,odds);const r=ranked;$('#analysis').hidden=false;$('#raceTitle').textContent=(names[r.venue]||r.venue_name||'직접 입력')+' '+r.race_no+'R';$('#raceMeta').textContent=[r.date,r.title,manual?'직접 입력 / 데모':''].filter(Boolean).join(' · ');$('#horseCount').textContent=r.horses.length+'두';$('#placeRule').textContent=r.k+'착 이내';$('#modeHelp').textContent=r.mode==='accuracy'?'추정 적중확률 순으로 추천합니다. 배당을 입력해도 순위는 바뀌지 않습니다.':'배당을 입력한 후보를 추정 기대수익률 순으로 정렬합니다. 적중확률은 낮아질 수 있습니다.';const warning=timingReasons(r);$('#raceWarning').hidden=!warning.length;$('#raceWarning').textContent=warning.join(' · ');$('#placeLead').innerHTML=pickHTML(r.places[0],r,'place',true);$('#pairLead').innerHTML=pickHTML(r.pairs[0],r,'pair',true);$('#placeList').innerHTML=r.places.slice(1,5).map(x=>pickHTML(x,r,'place')).join('');$('#pairList').innerHTML=r.pairs.slice(1,5).map(x=>pickHTML(x,r,'pair')).join('');$('#horses').innerHTML=r.horses.map(h=>`<div class="horse"><strong>${h.number} ${esc(h.name)} · ${probabilityHTML(h.prob)}</strong><p class="hint">${h.reasons.map(esc).join(' · ')}</p><p class="hint">레이팅 ${esc(h.rating??'—')} · 부담 ${esc(h.burden??'—')}kg · 마체중 ${esc(h.horse_weight??'미발표')} · 데이터 ${Math.round(h.quality*100)}%</p></div>`).join('');$('#savePrediction').disabled=manual||!Number.isFinite(start(r))||start(r)<=Date.now()||warning.length>0;renderOverview();}
function select(r,isManual=false){current=r;manual=isManual;odds={place:{},qpl:{}};$('#placeOdds').value='';$('#pairOdds').value='';if(names[r.venue])setVenue(r.venue);const d=String(r.date||'');if(/^\d{8}$/.test(d))$('#date').value=d.slice(0,4)+'-'+d.slice(4,6)+'-'+d.slice(6,8);if(r.race_no)$('#raceNo').value=r.race_no;$('#saveStatus').textContent='경주·추천 기준별 최초 기록을 보존합니다.';renderSelectors();render();}
async function fetchLiveDocument(){
 // Workflow commits do not rebuild branch-based Pages. Read the live data branch directly.
 const stamp=Date.now(),urls=['https://raw.githubusercontent.com/kkongt2/timeline/kra-mobile-pages/data/latest.json?t='+stamp,'data/latest.json?t='+stamp];
 let last;
 for(const url of urls){try{const res=await fetch(url,{cache:'no-store'});if(!res.ok)throw Error('HTTP '+res.status);const doc=await res.json();if(!Array.isArray(doc.races))throw Error('데이터 형식 오류');return doc;}catch(e){last=e;}}
 throw last;
}
async function load(){const id=++requestId;$('#dataStatus').textContent='경주 정보를 확인하는 중…';try{const doc=await fetchLiveDocument();if(id!==requestId)return false;source=doc;races=doc.races;$('#dataStatus').textContent=`갱신 ${doc.updated_at?.replace('T',' ').slice(0,16)||'시각 미확인'} · ${races.length}개 경주`;return true}catch(e){if(id===requestId)$('#dataStatus').textContent='불러오기 실패 · 새로고침을 눌러 다시 시도하세요.';return false}}
function parseOdds(text,pair){const out={};if(!text.trim())return out;for(const cell of text.split(',')){const m=cell.trim().match(pair?/^(\d+)-(\d+)\s*=\s*(\d+(?:\.\d+)?)$/:/^(\d+)\s*=\s*(\d+(?:\.\d+)?)$/);if(!m)throw Error('배당 형식을 확인하세요. 예: '+(pair?'2-7=3.4':'2=1.5'));const nums=pair?[+m[1],+m[2]]:[+m[1]],v=+(pair?m[3]:m[2]);if(v<1||!Number.isFinite(v)||new Set(nums).size!==nums.length||nums.some(n=>!ranked.horses.some(h=>+h.number===n)))throw Error('출전 마번과 1배 이상 배당을 입력하세요.');out[nums.sort((a,b)=>a-b).join('-')]=v;}return out;}
function save(){render();if($('#savePrediction').disabled)return;const r=ranked,key=[r.date,r.venue,r.race_no,r.mode].join(':');let all=records();if(all.some(x=>x.id===key)){$('#saveStatus').textContent='이미 기록한 경주입니다. 최초 추천을 유지합니다.';return}const copy=(x,t)=>({numbers:x.numbers,prob:x.prob,held:(r.mode==='value'?why(r,x,t):timingReasons(r)).length>0,selected:isSelected(r,t),selected_pick:isSelected(r,t)?{numbers:r.selectivePicks[t].numbers,prob:r.selectivePicks[t].prob,model:advancedReport.model}:null,model:r.models[t],selectionVersion:isSelected(r,t)?advancedReport?.dataset_sha256:null});all.push({id:key,date:r.date,venue:r.venue,race:r.race_no,mode:r.mode,model:r.model,historyThrough:r.history_through||null,saved:new Date().toISOString(),start:start(r),k:r.k,field:r.horses.map(h=>+h.number),place:copy(r.places[0],'place'),pair:copy(r.pairs[0],'pair'),result:null});if(put(all)){$('#saveStatus').textContent='기록했습니다. 경주 후 공식 결과를 입력하세요.';renderHistory();}}
function stat(all,type,mode,selectedOnly=false){const eligible=all.filter(x=>x.mode===mode&&!x[type].held&&(!selectedOnly||x[type].selected===true)),done=eligible.filter(x=>x.result),hit=done.filter(x=>selectedOnly&&x[type].selected_pick?x[type].selected_pick.numbers.every(n=>(type==='place'?x.result.placeWinners:x.result.finish).includes(n)):x.result[type+'Hit']).length,paid=done.filter(x=>!x.result[type+'Hit']||x.result[type+'Odds']!=null),returns=paid.reduce((s,x)=>s+(x.result[type+'Hit']?x.result[type+'Odds']:0),0);return `<div class="stat">${type==='place'?'연승':'복연승'} · ${mode==='accuracy'?(selectedOnly?'선별 후보':'전체 후보'):'수익성'}<b>${done.length?pct(hit/done.length):'—'}</b>${hit}/${done.length} 적중 · 대기 ${eligible.length-done.length}${selectedOnly?'':`<br>환수율 ${paid.length?pct(returns/paid.length):'—'} (${paid.length}건)`}</div>`;}
function renderHistory(){const all=records();$('#stats').innerHTML=['place','pair'].flatMap(t=>[stat(all,t,'accuracy'),stat(all,t,'accuracy',true)]).join('')+(['value'].flatMap(m=>all.some(x=>x.mode===m)?['place','pair'].map(t=>stat(all,t,m)):[]).join(''));$('#history').innerHTML=all.length?[...all].reverse().map(x=>`<details class="record"><summary>${esc(names[x.venue]||x.venue)} ${esc(x.date)} ${x.race}R · ${x.mode==='accuracy'?'적중률':'수익성'} ${x.result?'· 결과 입력됨':''}</summary><p>연승 ${x.place.numbers.join('-')}${x.place.held?' (보류)':''}${x.place.selected_pick?' · 별도 선별 '+x.place.selected_pick.numbers.join('-'):''} / 복연승 ${x.pair.numbers.join('-')}${x.pair.held?' (보류)':''}${x.pair.selected_pick?' · 별도 선별 '+x.pair.selected_pick.numbers.join('-'):''}</p><p>${esc(x.saved.replace('T',' ').slice(0,19))} UTC 저장 · 모델 ${esc(x.model)}</p>${x.result?`<p>공식 착순 ${x.result.finish.join(' → ')} · 연승 ${x.result.placeHit?'적중':'미적중'} / 복연승 ${x.result.pairHit?'적중':'미적중'}</p>`:''}<form data-record="${esc(x.id)}"><label>공식 1·2·3착 마번<input name="finish" required placeholder="예: 2,7,4" value="${x.result?.finish.join(',')||''}"></label><label>공식 연승 입상 마번 (취소로 기준이 바뀐 경우 수정)<input name="placeWinners" required placeholder="예: 2,7,4" value="${x.result?.placeWinners.join(',')||''}"></label><div class="result-fields"><label>추천 연승의 확정 배당<input name="placeOdds" type="number" min="1" step="0.01" placeholder="적중 시 입력" value="${x.result?.placeOdds??''}"></label><label>추천 복연승의 확정 배당<input name="pairOdds" type="number" min="1" step="0.01" placeholder="적중 시 입력" value="${x.result?.pairOdds??''}"></label></div><p class="hint">마사회 확정 결과를 확인해 입력하세요. 동착·환불 경주는 입력하지 마세요.</p><button type="submit" ${Date.now()<x.start?'disabled':''}>${x.result?'결과 수정':'결과 저장'}</button></form></details>`).join(''):'<p class="hint">아직 기록이 없습니다. 경주 전에 추천을 기록해 보세요.</p>';}
$('#history').addEventListener('submit',e=>{e.preventDefault();try{const f=e.target,all=records(),x=all.find(v=>v.id===f.dataset.record);if(!x||Date.now()<x.start)throw Error('경주 시작 후 입력할 수 있습니다.');const nums=v=>v.trim().split(/[,\s]+/).map(Number),finish=nums(f.elements.finish.value),pw=nums(f.elements.placeWinners.value);for(const a of [finish,pw])if(a.some(n=>!x.field.includes(n))||new Set(a).size!==a.length)throw Error('기록된 출전마의 서로 다른 마번을 입력하세요.');if(finish.length!==3||![2,3].includes(pw.length)||pw.some((n,i)=>n!==finish[i]))throw Error('착순 3두와 공식 연승 입상마 2~3두를 착순대로 입력하세요.');const odd=v=>v===''?null:Number(v),po=odd(f.elements.placeOdds.value),qo=odd(f.elements.pairOdds.value);if([po,qo].some(v=>v!==null&&(!Number.isFinite(v)||v<1)))throw Error('배당은 1 이상으로 입력하세요.');x.result={finish,placeWinners:pw,placeHit:pw.includes(x.place.numbers[0]),pairHit:x.pair.numbers.every(n=>finish.includes(n)),placeOdds:po,pairOdds:qo,entered:new Date().toISOString()};if(put(all))renderHistory();}catch(err){alert(err.message)}});
function venueDates(){return [...new Set(races.filter(r=>r.venue===venue&&/^\d{8}$/.test(String(r.date))).map(r=>String(r.date)))].sort();}
function dateRaces(d){return races.filter(r=>r.venue===venue&&String(r.date)===d).sort((a,b)=>+a.race_no-+b.race_no);}
function renderOverview(){
 const list=dateRaces($('#date').value.replaceAll('-',''));$('#overview').hidden=!list.length;
 let selected=0;
 $('#raceOverview').innerHTML=list.map(card=>{
  try{
   const r=analyze(card,'accuracy'),fresh=timingReasons(r).length===0;
   const has=kind=>fresh&&r.selection?.[kind]?.qualified;
   if(has('place')||has('pair'))selected++;
   const cell=kind=>{const x=kind==='place'?r.places[0]:r.pairs[0];return '<span><small>'+(kind==='place'?'연승':'복연승')+'</small><b>'+x.numbers.join(' – ')+'</b><small>'+probabilityHTML(x.prob)+'</small>'+(has(kind)?'<small class="selected-tag">선별 '+r.selectivePicks[kind].numbers.join('–')+'</small>':'')+officialResultHTML(card,kind)+'</span>'};
   return '<button type="button" class="overview-row '+(!manual&&current?.date===r.date&&+current?.race_no===+r.race_no?'active':'')+'" data-overview-race="'+Number(r.race_no)+'"><span><b>'+Number(r.race_no)+'R</b><small>'+esc(r.start_time||'')+'</small></span>'+cell('place')+cell('pair')+'</button>';
  }catch{return '<p class="hint">'+Number(card.race_no)+'R · 출전정보 확인 필요</p>'}
 }).join('');
 const enabled=['place','pair'].some(k=>advancedReport?.policies?.[k]?.approved);
 $('#overviewStatus').textContent='전체 '+list.length+'경주 · 선별 '+selected+'경주'+(enabled?' · 최신 정보가 확인된 출발 전 경주만 선별 표시':' · 검증을 통과한 선별 기준이 아직 없어 일반 후보만 표시');
}
$('#raceOverview').addEventListener('click',e=>{const b=e.target.closest('button[data-overview-race]');if(!b)return;const r=dateRaces($('#date').value.replaceAll('-','')).find(x=>+x.race_no===+b.dataset.overviewRace);if(r)select(r);});
function renderSelectors(){
 const dates=venueDates(),selected=$('#date').value.replaceAll('-','');let month='';
 $('#dateCalendar').innerHTML=dates.length?dates.map(d=>{
  const key=d.slice(0,6),heading=month!==key?'<div class="calendar-month">'+d.slice(0,4)+'년 '+Number(d.slice(4,6))+'월</div>':'';month=key;
  const weekday=new Intl.DateTimeFormat('ko-KR',{weekday:'short',timeZone:'Asia/Seoul'}).format(new Date(d.slice(0,4)+'-'+d.slice(4,6)+'-'+d.slice(6,8)+'T12:00:00+09:00'));
  return heading+'<button type="button" data-date="'+d+'" aria-pressed="'+(d===selected)+'" aria-label="'+d.slice(0,4)+'년 '+Number(d.slice(4,6))+'월 '+Number(d.slice(6,8))+'일 '+weekday+'요일" class="date-choice '+(d===selected?'active':'')+'"><span>'+weekday+'</span><strong>'+Number(d.slice(6,8))+'</strong></button>';
 }).join(''):'<p class="hint">이 지역에 공개된 경주일이 없습니다.</p>';
 const list=dateRaces(selected);$('#raceButtons').innerHTML=list.length?list.map(r=>'<button type="button" data-race="'+Number(r.race_no)+'" aria-pressed="'+(+r.race_no===+$('#raceNo').value)+'" class="race-choice '+(+r.race_no===+$('#raceNo').value?'active':'')+'">'+Number(r.race_no)+'R</button>').join(''):'<p class="hint">선택 가능한 경주가 없습니다.</p>';
}
function chooseAvailable(){
 const dates=venueDates();let d=$('#date').value.replaceAll('-','');if(!dates.includes(d))d=dates.find(x=>x>=day().replaceAll('-',''))||dates.at(-1)||'';
 $('#date').value=d?d.slice(0,4)+'-'+d.slice(4,6)+'-'+d.slice(6,8):'';
 const list=dateRaces(d),r=list.find(x=>+x.race_no===+$('#raceNo').value)||list[0];
 if(r)select(r);else{current=null;ranked=null;$('#analysis').hidden=true;$('#raceNo').value='';renderSelectors();renderOverview();}
}
$('#date').value=day();$('#raceNo').value='1';renderSelectors();
document.querySelectorAll('[data-venue]').forEach(b=>b.onclick=()=>{setVenue(b.dataset.venue);chooseAvailable();});
function showSelected(){chooseAvailable();}
$('#dateCalendar').addEventListener('click',e=>{const b=e.target.closest('button[data-date]');if(!b||!venueDates().includes(b.dataset.date))return;const d=b.dataset.date;$('#date').value=d.slice(0,4)+'-'+d.slice(4,6)+'-'+d.slice(6,8);$('#raceNo').value='1';chooseAvailable();});
$('#raceButtons').addEventListener('click',e=>{const b=e.target.closest('button[data-race]');if(!b)return;const r=dateRaces($('#date').value.replaceAll('-','')).find(x=>+x.race_no===+b.dataset.race);if(r)select(r);});
$('#loadBtn').onclick=async()=>{if(await load())chooseAvailable();await loadProspective()};$('#nextBtn').onclick=async()=>{if(!await load())return;const future=races.filter(x=>x.venue===venue&&start(x)>Date.now()).sort((a,b)=>start(a)-start(b));if(future[0])select(future[0]);else{chooseAvailable();$('#dataStatus').textContent='선택 경마장의 예정 경주가 없습니다.';}};
$('#mode').onchange=render;$('#applyOdds').onclick=()=>{try{const next={place:parseOdds($('#placeOdds').value,false),qpl:parseOdds($('#pairOdds').value,true)};odds=next;render()}catch(e){alert(e.message)}};$('#savePrediction').onclick=save;$('#manualBtn').onclick=()=>{try{const r=JSON.parse($('#manualJson').value);analyze(r);select(r,true)}catch(e){alert('출전마 JSON을 확인하세요. '+e.message)}};
$('#demoBtn').onclick=()=>select({venue,date:day().replaceAll('-',''),race_no:1,title:'데모 · 실제 경주 아님',horses:Array.from({length:8},(_,i)=>({number:i+1,name:'샘플 '+(i+1),rating:50-i*2,burden:54,starts_1y:10,wins_1y:i<2?2:0,seconds_1y:2,thirds_1y:1,distance_starts:5,distance_top3:i<3?3:1,recent_finishes:[i+1,3,5],jockey_stats_1y:{place_rate:.3},trainer_stats_1y:{place_rate:.25},horse_weight:480}))},true);
$('#lockBtn').onclick=()=>{$('#lockScreen').hidden=false;$('#pinInput').focus()};$('#unlockBtn').onclick=()=>{if($('#pinInput').value==='1234'){$('#lockScreen').hidden=true;$('#pinInput').value='';$('#lockError').textContent=''}else $('#lockError').textContent='PIN이 다릅니다.';};
async function loadTraining(){
 try{
  const res=await fetch('data/training-report.json',{cache:'no-store'});if(!res.ok)throw Error();const r=await res.json();setTrainedModel(r);
  if(!r.counts||!r.baseline||!r.candidate)throw Error();
  const c=r.counts,format=x=>(x*100).toFixed(1)+'%';
  $('#trainingStatus').innerHTML='<p><b>'+c.collected_races.toLocaleString()+'개 경주 · '+c.horse_starts.toLocaleString()+'회 출전</b><br>'+esc(r.period.from)+' ~ '+esc(r.period.to)+'</p><p>학습 '+c.training_races.toLocaleString()+' / 조정 '+c.validation_races.toLocaleString()+' / 최종 평가 '+c.test_races.toLocaleString()+'<br>이전 전적 구성 '+(c.collected_races-c.training_races-c.validation_races-c.test_races).toLocaleString()+'개 경주</p><p>평가 기간 '+esc(r.period.test)+'</p><p>연승 1순위: 기존 '+format(r.baseline.place_hit_rate)+' → 학습 '+format(r.candidate.place_hit_rate)+'<br>복연승 1순위: 기존 '+format(r.baseline.pair_hit_rate)+' → 학습 '+format(r.candidate.pair_hit_rate)+'</p><p>'+(r.approved?'학습 모델 적용: '+r.approved_venues.map(v=>esc(names[v]||v)).join(', '):'개선이 충분히 확인되지 않아 기본 모델 유지')+'</p><p>과거 재현 평가입니다. 앞으로의 적중률을 보장하지 않으며, 보류 조건을 적용하기 전 전체 평가 경주 기준입니다. 배당·당일 착순은 학습 입력에서 제외했습니다.</p>';
 }catch{$('#trainingStatus').textContent='대량 학습의 검증 성적이 아직 없습니다. 현재는 기본 모델을 사용합니다.';}
}
async function loadAdvanced(){
 try{const res=await fetch('data/model-v6.json',{cache:'no-store'});if(!res.ok)return;const r=await res.json();if(setAdvancedModel(r))advancedReport=r;}
 catch{advancedReport=null;setAdvancedModel(null);}
}
function renderAdvancedReport(){
 const r=advancedReport;if(!r)return;
 const c=r.counts,rate=x=>Number.isFinite(x)?pct(x):'—',metric=s=>s?.races?rate(s.hit_rate)+' ('+s.hits+'/'+s.races+')':'표본 없음';
 const kinds=['place','pair'];
 const table='<table class="validation-table"><thead><tr><th>승식</th><th>전체 후보</th><th>선별 후보</th><th>선별 비율</th></tr></thead><tbody>'+kinds.map(k=>{const p=r.policies[k],on=p.approved;return '<tr><th>'+(k==='place'?'연승':'복연승')+'</th><td>'+metric(r.deployment[k].approved?p.audit_all:r.deployment[k].incumbent)+'</td><td>'+(on?metric(p.audit_selected):'검증 대기')+'</td><td>'+(on?rate(p.audit_coverage):'—')+'</td></tr>'}).join('')+'</tbody></table>';
 $('#trainingStatus').innerHTML='<p><b>'+c.collected_races.toLocaleString()+'개 경주 · '+c.horse_starts.toLocaleString()+'회 출전</b><br>'+esc(r.period.from)+' ~ '+esc(r.period.to)+'</p><p>첫해 전적 구성 '+c.warmup_races.toLocaleString()+'경주 · 추가 품질 검사 제외 '+c.excluded_races+'경주</p><p>'+kinds.map(k=>(k==='place'?'연승':'복연승')+' 학습 '+c.training_races[k].toLocaleString()+'경주').join(' · ')+'<br>확률 보정 '+c.calibration_races+' · 선별 기준 설정 '+c.selection_races+' · 별도 확인 '+c.confirmation_races+'경주</p><p>'+kinds.map(k=>{const d=r.deployment[k];return (k==='place'?'연승':'복연승')+': '+(d.approved?'조건별 학습 모델 적용':'기존 모델 유지 · 신규 모델 교체 기준 미달')}).join('<br>')+'</p><p><b>과거 재평가</b> · '+esc(r.period.audit)+'</p>'+table+'<p>전체 후보와 선별 후보는 별도 모델을 사용하며 추천마가 다를 수 있습니다. 이 기간은 이전 모델 평가에도 사용했습니다. 새로운 독립 검증 또는 실전 성적이 아닙니다.</p><details><summary>선별 기준과 별도 확인 성적</summary>'+kinds.map(k=>{const p=r.policies[k],t=p.criteria,d=r.deployment[k];return '<p><b>'+(k==='place'?'연승':'복연승')+'</b> · '+(p.approved?'선별 표시 사용':'선별 표시 대기')+'<br>확인 기간 '+esc(r.period.confirmation)+'<br>전체 '+metric(p.all)+' → 선별 '+metric(p.selected)+' · 비율 '+rate(p.coverage)+(t?'<br>확률 '+rate(t.min_probability)+' 이상 · 다음 후보와 '+rate(t.min_gap)+' 이상 차이'+(t.min_starts?' · 과거 출전 '+t.min_starts+'회 이상':''):'')+'<br>대상 지역 '+(p.approved_venues.map(v=>names[v]||v).join(', ')||'없음')+'</p>'}).join('')+'</details><details><summary>학습 방식 비교</summary>'+kinds.map(k=>'<p><b>'+(k==='place'?'연승':'복연승')+'</b> · '+esc(r.comparison[k].chosen)+' 선택</p><table class="validation-table"><thead><tr><th>방식</th><th>기간 이동 평가 적중률</th></tr></thead><tbody>'+r.comparison[k].candidates.map(x=>'<tr><td>'+esc(({linear_all:'전체 기간 · 선형',tree_1y:'최근 1년',tree_3y:'최근 3년',tree_all:'전체 기간 · 조건별',tree_recent:'최근 기록 가중'})[x.config.name]||x.config.name)+'</td><td>'+rate(x.hit_rate)+'</td></tr>').join('')+'</tbody></table>').join('')+'</details><details><summary>예측 확률과 실제 적중률</summary>'+kinds.map(k=>'<p><b>'+(k==='place'?'연승':'복연승')+'</b> · 신규 후보 모델 과거 재평가</p><table class="validation-table"><thead><tr><th>예측 평균</th><th>실제 적중</th><th>경주 수</th></tr></thead><tbody>'+r.policies[k].audit_reliability.filter(x=>x.races).map(x=>'<tr><td>'+rate(x.predicted)+'</td><td>'+rate(x.actual)+'</td><td>'+x.races+'</td></tr>').join('')+'</tbody></table>').join('')+'</details><p>배당·당일 결과·당일 마체중은 학습 입력에서 제외했습니다. 선별은 추천 횟수를 줄이는 방식이며 수익성을 뜻하지 않습니다. 실제 기록 성적은 아래에서 따로 확인합니다.</p>';
}
async function fetchPublicJSON(path){
 for(const url of ['https://raw.githubusercontent.com/kkongt2/timeline/kra-mobile-pages/'+path,path]){
  try{const res=await fetch(url+'?t='+Date.now(),{cache:'no-store'});if(res.ok)return await res.json();}catch{}
 }
 throw Error('불러오기 실패');
}
async function loadChallenger(){
 try{
  const r=await fetchPublicJSON('data/model-v7.json');if(!setChallengerModel(r))return;
  const metric=x=>x?.races?pct(x.hit_rate)+' ('+x.hits+'/'+x.races+')':'—';
  $('#challengerStatus').innerHTML='<p><b>과거 성적·경주 전개 개선 모델</b><br>'+r.counts.races.toLocaleString()+'개 경주 · 실제 연승 입상·거리·등급 지표와 구간 기록을 추가한 모델 비교</p><p>과거 재평가 '+esc(r.periods.audit)+' · 앞선 연구에도 사용한 기간입니다.</p>'+['place','pair'].map(k=>'<p><b>'+(k==='place'?'연승':'복연승')+'</b> · 기존 '+metric(r.deployment[k].incumbent)+' → 새 모델 '+metric(r.deployment[k].candidate)+'<br>'+(r.deployment[k].approved?'교체 기준 통과 · 일반 추천에 적용':'교체 기준 미달 · 기존 추천 유지, 새 모델은 사전 비교 기록')+'</p>').join('')+'<p>구간 기록이 없는 말은 누락 상태를 반영합니다. 과거 말 식별은 이름·출생 연도 추정·성별을 함께 사용하며, 개명 이력은 연결되지 않을 수 있습니다.</p>';
 }catch{$('#challengerStatus').textContent='개선 모델의 검증 결과를 불러오지 못했습니다.';}
}
async function loadProspective(){
 try{
  const s=await fetchPublicJSON('data/prediction-summary.json');if(s.schema!==1||!Array.isArray(s.groups))throw Error();
  const label={general:'일반 추천',challenger:'새 모델 비교',selective:'선별 추천',incumbent:'기존 모델 비교'};
  $('#autoStats').innerHTML='<p>경주 전 자동 기록 <b>'+s.recorded_races+'경주</b> · 지난 경주의 재계산 후보는 포함하지 않습니다.</p>'+(s.groups.length?'<table class="validation-table"><thead><tr><th>모델·승식</th><th>실제 적중</th><th>대기</th></tr></thead><tbody>'+s.groups.map(g=>'<tr><td>'+label[g.track]+' · '+(g.kind==='place'?'연승':'복연승')+'<br><small>'+esc(g.model)+' · '+esc(g.bundle_hash.slice(0,6))+'</small></td><td>'+(g.settled?pct(g.hit_rate)+'<br>'+g.hits+'/'+g.settled:'표본 없음')+'</td><td>'+g.pending+(g.void?'<br>환불·제외 '+g.void:'')+'</td></tr>').join('')+'</tbody></table>':'<p>다음 경주부터 사전 기록이 쌓입니다.</p>');
  if(s.paired?.length)$('#autoStats').innerHTML+='<p><b>같은 경주에서 비교</b><br>'+s.paired.map(p=>(p.kind==='place'?'연승':'복연승')+' '+p.races+'경주 · 기존 '+p.baseline_hits+'적중 → 새 모델 '+p.challenger_hits+'적중').join('<br>')+'</p>';
  $('#autoHistory').innerHTML=s.recent.slice(0,20).map(r=>'<div class="auto-record"><b>'+esc(r.date)+' '+esc(names[r.venue])+' '+r.race_no+'R</b><p class="hint">기록 '+new Date(r.saved_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'})+'</p>'+Object.entries(r.tracks).map(([track,t])=>'<p>'+label[track]+'<br>'+['place','pair'].filter(k=>t[k]).map(k=>{const x=t[k];return (k==='place'?'연승 ':'복연승 ')+x.numbers.join('–')+' · '+pct(x.prob)+' · '+(x.status==='settled'?(x.hit?'적중 '+x.odds.toFixed(1)+'배':'미적중'):x.status==='void'?'환불·제외':'결과 대기');}).join('<br>')+'</p>').join('')+'</div>').join('')||'<p class="hint">아직 자동 사전 기록이 없습니다.</p>';
 }catch{$('#autoStats').textContent='자동 사전 기록을 불러오지 못했습니다.';}
}
renderHistory();Promise.all([load(),loadTraining(),loadAdvanced(),loadChallenger(),loadProspective()]).then(([ok])=>{renderAdvancedReport();if(!ok)return;const future=races.filter(x=>start(x)>Date.now()).sort((a,b)=>start(a)-start(b));if(future[0])select(future[0]);else showSelected()});
// Expire selection badges even when the user keeps the page open across the start time.
if(typeof setInterval==='function')setInterval(()=>{if(current)render();},60000);
document.addEventListener?.('visibilitychange',()=>{if(!document.hidden&&current)render();});
