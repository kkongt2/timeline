'use strict';
const $=id=>document.getElementById(id),venues={seoul:'서울',busan:'부산경남',jeju:'제주'};
const state={venue:'seoul',date:null,round:null,doc:null,model:null,report:null};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct=(x,d=1)=>Number.isFinite(x)?`${(x*100).toFixed(d)}%`:'—';
const money=(n,sign=false)=>Number.isFinite(n)?`${sign&&n>0?'+':''}${Math.round(n).toLocaleString('ko-KR')}원`:'—';
const colored=x=>x>=0?'positive':'negative';
const today=()=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date()).replace(/-/g,'');
const dateLabel=s=>`${Number(s.slice(4,6))}.${Number(s.slice(6,8))} (${new Intl.DateTimeFormat('ko-KR',{weekday:'short',timeZone:'Asia/Seoul'}).format(new Date(`${s.slice(0,4)}-${s.slice(4,6)}-${s.slice(6,8)}T12:00:00+09:00`))})`;
const key=c=>c.numbers.join('-');
function chart(items){
  if(!items.length)return '';
  const vals=[0,...items.map(x=>x.profit_units*1000)],lo=Math.min(...vals),hi=Math.max(...vals),span=hi-lo||1;
  const y=v=>112-(v-lo)/span*100,x=i=>10+i/(vals.length-1)*780;
  const points=vals.map((v,i)=>`${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  return `<svg class="chart" viewBox="0 0 800 130" role="img" aria-label="분리 평가 기간의 일별 누적 세전 손익"><line x1="10" y1="${y(0)}" x2="790" y2="${y(0)}" stroke="#cdd7cc" stroke-dasharray="4 5"/><polyline points="${points}" fill="none" stroke="${vals.at(-1)>=0?'#327557':'#aa5346'}" stroke-width="2.5" vector-effect="non-scaling-stroke"/><circle cx="790" cy="${y(vals.at(-1))}" r="4" fill="#327557"/></svg>`;
}
function evidence(){
  const r=state.report,e=r.evaluation,s=r.selection,b=r.baseline;
  $('verified').textContent=r.approved?'분리 평가 기준 통과':'흑자 검증 불충분';$('verified').className=`pill ${r.approved?'':'warning'}`;
  $('metrics').innerHTML=`<div class="metric"><span>누적 세전 손익</span><strong class="${colored(e.profit_krw)}">${money(e.profit_krw,true)}</strong></div><div class="metric"><span>수익률 · ROI</span><strong class="${colored(e.roi)}">${e.roi>0?'+':''}${pct(e.roi,2)}</strong></div><div class="metric"><span>일별 최대 낙폭</span><strong>${money(e.daily_max_drawdown_krw)}</strong></div>`;
  $('chart').innerHTML=chart(e.curve);
  $('evaluation-note').textContent=`2026.01.01–2026.09.10 · ${e.bets.toLocaleString()}조합 × 1,000원 · 총 베팅 ${money(e.stake_krw)}. 과거 재계산 결과이며 실제 사전 예측 실적이 아닙니다.`;
  $('validation').innerHTML=`<p>수익률 95% 신뢰구간: <strong>${pct(e.roi_95ci[0],2)} ~ ${pct(e.roi_95ci[1],2)}</strong><br>적중률 ${pct(e.hit_rate)} · 적중 시 평균 배당 ${e.mean_hit_dividend?.toFixed(2)??'—'}배<br>최장 연속 손실 ${e.max_losing_days}경기일 · 최고 수익일을 제외한 손익 ${money(e.without_best_day_profit_krw,true)}</p><table><thead><tr><th>평가 월</th><th>조합 수</th><th>세전 손익</th></tr></thead><tbody>${e.months.map(m=>`<tr><td>${m.month.slice(0,4)}.${m.month.slice(4)}</td><td>${m.bets}</td><td class="${colored(m.profit_krw)}">${money(m.profit_krw,true)}</td></tr>`).join('')}</tbody></table><p>조건 선택 구간(2025.04–12): ${s.bets}조합, ${money(s.profit_krw,true)} (${pct(s.roi,2)}).<br>비교 기준: 매 경주 적중확률 1위 조합에 1,000원씩 베팅하면 ${b.bets}조합, ${money(b.profit_krw,true)} (${pct(b.roi,2)}). 베팅 횟수가 다르므로 총액과 수익률을 함께 비교해야 합니다.</p><p>2026년 자료는 이번 수익 조건 선택에서 제외했습니다. 다만 이전 적중률 연구에서 사용된 기간이므로 완전히 새로운 독립 표본은 아닙니다.</p>`;
  $('policy').textContent=`연구 조건: 기대수익률 ${pct(r.policy.min_edge,0)} 이상 중 경주당 상위 ${r.policy.max_per_race}조합. 조건 선택 구간의 총 세전 순손익으로 48개 조건을 비교했습니다. ${r.approved?'분리 평가 통과 조건입니다.':'현재 흑자 검증을 통과하지 못해 베팅 추천은 보류합니다. 아래 조합은 연구 후보입니다.'}`;
  $('method').innerHTML=`<p>공식 보고서 1,620개 · 경주 이력 ${r.counts.history_races.toLocaleString()}건 · 배당 확인 ${r.counts.payout_races.toLocaleString()}건.<br>2021년은 이력 축적에 사용했습니다. 분석 대상 ${r.counts.used_races.toLocaleString()}경주 / ${r.counts.pairs.toLocaleString()}조합.<br>학습: 2022–2024년 ${r.counts.fit_races.toLocaleString()}경주<br>확률·배당 보정: 2025.01–03 ${r.counts.calibration_races}경주<br>조건 선택: 2025.04–12 ${r.counts.selection_races.toLocaleString()}경주<br>분리 평가: 2026.01–09.10 ${r.counts.evaluation_races.toLocaleString()}경주</p><p>각 경기일보다 앞선 이력만 입력합니다. 확정 배당은 학습 목표와 손익 정산에만 쓰며, 선택 시점에는 미래의 실제 배당을 사용하지 않습니다. 결측 배당과 해석이 불명확한 경주는 제외하며 미적중으로 처리하지 않습니다.</p><p>수익은 공식 환급 배당에서 원금을 뺀 세전 금액입니다. 배당에 이미 반영된 공제율은 다시 차감하지 않으며, 개인별 적중금 세금·입장 비용은 포함하지 않았습니다. 모든 조합에 1,000원을 고정하고 복리·증액 베팅은 하지 않습니다.</p><p>흑자 표시 조건: 선택 구간 흑자, 분리 평가 200조합·60경기일 이상, 날짜 단위 재표집 수익률 95% 신뢰구간 하한이 0 초과, 최고 수익일을 빼도 흑자. 검증에 실패하면 베팅하지 않는 상태를 유지합니다. 비교한 48개 조건 밖에서의 최적 수익은 확인하지 않았습니다.</p>`;
}
function button(label,value,selected,action){const b=document.createElement('button');b.type='button';b.textContent=label;b.setAttribute('aria-pressed',String(value===selected));b.addEventListener('click',()=>action(value));return b;}
function selectors(){
  const all=state.doc.races.filter(r=>r.venue===state.venue),dates=[...new Set(all.map(r=>r.date))].sort();
  if(!dates.includes(state.date))state.date=dates.includes(today())?today():dates.find(d=>d>today())||dates.at(-1);
  const races=all.filter(r=>r.date===state.date).sort((a,b)=>a.race_no-b.race_no);
  if(!races.some(r=>r.race_no===state.round))state.round=races[0]?.race_no;
  $('venues').replaceChildren(...Object.entries(venues).map(([v,name])=>button(name,v,state.venue,x=>{state.venue=x;selectors();})));
  $('dates').replaceChildren(...dates.map(d=>button(dateLabel(d),d,state.date,x=>{state.date=x;state.round=null;selectors();})));
  $('rounds').replaceChildren(...races.map(r=>button(`${r.race_no}R`,r.race_no,state.round,x=>{state.round=x;selectors();})));
  renderRace(races.find(r=>r.race_no===state.round));
}
function candidate(c,i,preferred){
  return `<article class="candidate ${preferred?'preferred':''}"><div class="candidate-top"><div><p class="rank">${preferred?'조건 충족 · ':''}${state.model.approved?'후보':'연구 후보'} ${i+1}</p><div class="numbers"><span class="horse-number">${c.numbers[0]}</span><span>—</span><span class="horse-number">${c.numbers[1]}</span></div><p class="names">${c.names.map(esc).join(' · ')}</p></div><div class="edge"><span>추정 기대수익률</span><strong class="${colored(c.edge)}">${c.edge>0?'+':''}${pct(c.edge)}</strong></div></div><div class="candidate-stats"><div><span>추정 적중확률</span><strong>${pct(c.prob)}</strong></div><div><span>예상 배당 · 모델 추정</span><strong>${c.dividend.toFixed(2)}배</strong></div><div><span>손익분기 배당 · 1/p</span><strong>${c.break_even.toFixed(2)}배</strong></div></div></article>`;
}
function renderRace(r){
  const age=(Date.now()-Date.parse(state.doc.updated_at))/60000,fresh=Number.isFinite(age)&&age>=-5&&age<=30;
  $('freshness').textContent=`데이터 갱신: ${new Date(state.doc.updated_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'})} (한국시간)${fresh?'':' · 갱신 필요'}`;
  if(!r){$('race-content').innerHTML='<div class="empty">이 지역에서 확인된 경주 일정이 없습니다.</div>';return;}
  const d=r.date,start=/^\d{2}:\d{2}$/.test(r.start_time||'')?Date.parse(`${d.slice(0,4)}-${d.slice(4,6)}-${d.slice(6,8)}T${r.start_time}:00+09:00`):NaN;
  const ended=r.historical_view||r.date<today()||Number.isFinite(start)&&Date.now()>=start;
  let html=`<div class="race-heading"><div><h3>${esc(venues[r.venue])} ${r.race_no}경주</h3><p>${esc(r.grade||'')} · ${r.distance}m · ${r.horses.length}두 · ${esc(r.start_time||'시각 미확인')}</p></div><span class="pill">${ended?'출발 시각 경과':'예정 경주'}</span></div>`;
  if(ended){
    const result=r.official_result,pp=result?.pair;
    html+=`<div class="notice">지난 경주는 공식 결과만 표시합니다.</div>`;
    if(pp?.status==='confirmed'&&Array.isArray(pp.payouts))html+=`<div class="panel"><h2>복연승 실제 결과</h2><table><thead><tr><th>적중 조합</th><th>확정 배당</th></tr></thead><tbody>${pp.payouts.map(p=>`<tr><td>${p.numbers.map(esc).join(' — ')}</td><td>${Number(p.odds).toFixed(1)}배</td></tr>`).join('')}</tbody></table></div>`;
    else html+=`<div class="empty">${pp?.status==='refund'?'복연승 환불 경주입니다.':'공식 복연승 결과가 아직 확인되지 않았습니다.'}</div>`;
  }else{
    const cs=QPL.predict(r,state.model),chosen=QPL.selection(cs,state.model),keys=new Set(chosen.map(key));
    const recommend=state.model.approved&&fresh&&Number.isFinite(start);
    html+=`<div class="notice">${!fresh?'데이터가 오래되었습니다. 갱신 후 판단해 주세요. ':''}${recommend?(chosen.length?'검증 기준을 통과한 조건의 조합입니다.':'현재 연구 조건을 충족하는 조합이 없습니다.'):state.model.approved?'경주 시각·데이터 상태 확인이 필요해 추천을 보류합니다.':'장기 흑자 검증이 부족해 베팅 추천을 보류합니다. 연구 후보를 기대수익 순으로 표시합니다.'} 예상 배당은 실제 시세와 다를 수 있습니다.</div>`;
    if(cs.length){
      html+=`<div class="candidate-grid">${cs.slice(0,2).map((c,i)=>candidate(c,i,keys.has(key(c)))).join('')}</div>`;
      if(cs.length>2)html+=`<details class="list-more"><summary>나머지 ${cs.length-2}개 조합 보기</summary>${cs.slice(2).map((c,i)=>candidate(c,i+2,keys.has(key(c)))).join('')}</details>`;
    }else html+='<div class="empty">경주 이력이 부족하거나 오래되어 추정치를 표시할 수 없습니다.</div>';
  }
  $('race-content').innerHTML=html;
}
async function json(path){const r=await fetch(`${path}?t=${Date.now()}`,{cache:'no-store'});if(!r.ok)throw Error(`${path} 불러오기 실패`);return r.json();}
async function load(){
  $('refresh').disabled=true;
  try{
    const [doc,model,report]=await Promise.all([json('data/latest.json'),json('data/model.json'),json('data/backtest.json')]);
    if(!Array.isArray(doc.races)||!doc.updated_at||report.schema!==1||model.schema!==1||model.approved!==report.approved||JSON.stringify(model.policy)!==JSON.stringify(report.policy))throw Error('데이터·모델 버전이 맞지 않습니다.');
    Object.assign(state,{doc,model,report});evidence();selectors();
  }catch(e){$('race-content').innerHTML=`<div class="empty">${esc(e.message)}<br>잠시 후 새로고침해 주세요.</div>`;$('freshness').textContent='데이터를 새로 확인하지 못했습니다.';}
  finally{$('refresh').disabled=false;}
}
$('refresh').addEventListener('click',load);setInterval(()=>{if(state.doc)selectors();},60000);load();
