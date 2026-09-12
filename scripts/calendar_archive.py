"""Extend browsing to the previous two full weeks, without forecast backfill."""
import gzip,json,re,sys
from collections import defaultdict
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

def window_start(now):return (now-timedelta(days=now.weekday()+14)).strftime('%Y%m%d')
def race_key(r):return (r['date'],r['venue'],int(r['race_no']))

def extend(races,now):
    floor=window_start(now);cutoff=(now-timedelta(days=2)).strftime('%Y%m%d')
    cards={race_key(r):r for r in races if r['date']>=floor}
    path=Path('data/calendar-archive.json')
    if path.exists():
        for r in json.loads(path.read_text())['races']:
            if floor<=r['date']<cutoff:cards.setdefault(race_key(r),r)
    return sorted(cards.values(),key=race_key)

def dividends(block,kind,expected):
    circles={chr(0x2460+i):i+1 for i in range(20)}
    heading=re.search(r'배당률\s+단:',block)
    if not heading:raise ValueError('Missing dividend heading')
    tail=block[heading.end():]
    match=re.search(r'\s연:\s*(.*?)\s+복:',tail,re.S) if kind=='place' else re.search(r'복연:\s*([^\r\n]+)',tail)
    if not match:raise ValueError('Missing '+kind+' dividends')
    value=match[1].strip();pattern=r'([①-⑳])\s*(\d+(?:\.\d+)?)' if kind=='place' else r'([①-⑳])\s*([①-⑳])\s*(\d+(?:\.\d+)?)'
    result=[];seen=set()
    for parts in re.findall(pattern,value):
        ns=sorted(circles[c] for c in parts[:-1]);odds=float(parts[-1]);key=tuple(ns)
        if odds<1 or len(set(ns))!=len(ns) or key in seen:raise ValueError('Invalid payout')
        seen.add(key);result.append(dict(numbers=ns,odds=odds))
    if re.sub(pattern,'',value).strip() or seen!=set(expected):raise ValueError('Dividend winners mismatch')
    return dict(status='confirmed',payouts=result)

def bootstrap():
    from itertools import combinations
    sys.path.insert(0,str(Path(__file__).parent/'model-research'))
    from collect import VENUES
    from update_kra import parse_card,S,decode_response
    from results_kra import attach_results
    now=datetime.now(ZoneInfo('Asia/Seoul'));floor=window_start(now);cutoff=(now-timedelta(days=2)).strftime('%Y%m%d')
    root=Path('_archive_seed/training')
    rows=[json.loads(x) for x in gzip.decompress((root/'history-v7.jsonl.gz').read_bytes()).splitlines()]
    manifest=json.loads((root/'manifest.json').read_text());report_index={(r['date'],VENUES[r['meet']]):r for r in manifest['reports']}
    horses=defaultdict(list);people=defaultdict(list)
    for r in sorted(rows,key=race_key):
        day=datetime.strptime(r['date'],'%Y%m%d').toordinal()
        for h in r['horses']:
            horses[r['venue'],h['name']].append((day,h['finish'],r['distance']))
            for kind in ['jockey','trainer']:people[r['venue'],kind,h[kind]].append((day,h['finish']))
    def decorate(card):
        day=datetime.strptime(card['date'],'%Y%m%d').toordinal()
        for h in card['horses']:
            hist=[x for x in horses[card['venue'],h['name']] if x[0]<day];year=[x for x in hist if x[0]>=day-365];dist=[x for x in hist if x[2]==card['distance']]
            h.update(starts_1y=len(year),wins_1y=sum(x[1]==1 for x in year),seconds_1y=sum(x[1]==2 for x in year),thirds_1y=sum(x[1]==3 for x in year),
                distance_starts=len(dist),distance_top3=sum(x[1]<=3 for x in dist),recent_finishes=[x[1] for x in hist[-5:][::-1]],interval_weeks=(day-hist[-1][0])/7 if hist else 0)
            for kind in ['jockey','trainer']:
                values=[x[1] for x in people[card['venue'],kind,h[kind]] if day-365<=x[0]<day]
                h[kind+'_stats_1y']={'place_rate':sum(v<=3 for v in values)/len(values) if values else .3}
        card.update(historical_view=True,calendar_archive=True,prediction_view='historical_recalculation')
        card['title']=f"{card.get('grade') or ''} · {card['distance']}M · 과거 이력 재계산"
        return card
    cards={};texts={}
    for r in rows:
        if not floor<=r['date']<cutoff:continue
        report=report_index[r['date'],r['venue']];source_key=(report['meet'],r['date'])
        if source_key not in texts:
            p=Path('training/raw')/str(report['meet'])/(r['date']+'.txt.gz')
            texts[source_key]=gzip.decompress(p.read_bytes()).decode()
        blocks=re.split(r'(?=제목\s*:\s*\d{2,4}년)',texts[source_key])
        matches=[b for b in blocks if (m:=re.search(r'제목\s*:\s*(\d{2,4})년\s*(\d+)월\s*(\d+)일.*?제\s*(\d+)경주',b)) and int(m[4])==r['race_no']]
        if len(matches)!=1:raise ValueError(f'Expected one report block: {r["date"]} {r["venue"]} {r["race_no"]}; headings '+repr([b[:150] for b in blocks[:3]]))
        block=matches[0]
        card={k:r[k] for k in ['date','venue','race_no','distance','grade']};card['start_time']=''
        card['horses']=[{k:h[k] for k in ['number','name','age','sex','rating','burden','jockey','trainer','horse_weight','horse_weight_change'] if k in h} for h in sorted(r['horses'],key=lambda h:h['number'])]
        winners=[h['number'] for h in sorted(r['horses'],key=lambda h:h['finish'])[:3]]
        card['official_result']=dict(status='confirmed',version=2,source=report['source'],checked_at=now.isoformat(timespec='seconds'),starters=[h['number'] for h in card['horses']],
            place=dividends(block,'place',[(n,) for n in r['place_winners']]),pair=dividends(block,'pair',[tuple(sorted(p)) for p in combinations(winners,2)]))
        cards[race_key(card)]=decorate(card)
    for report in manifest['reports']:
        if not floor<=report['date']<cutoff:continue
        for rn,_ in report.get('skips',[]):
            key=(report['date'],VENUES[report['meet']],int(rn))
            if key in cards:continue
            card,_=parse_card(report['date'],rn,report['meet'])
            if not card:raise ValueError('Missing historical card '+str(key))
            attach_results([card],{},now,S,decode_response)
            if card.get('official_result',{}).get('status')!='confirmed':raise ValueError('Missing historical result '+str(key))
            cards[key]=decorate(card)
    out=dict(from_date=floor,races=sorted(cards.values(),key=race_key))
    Path('data/calendar-archive.json').write_text(json.dumps(out,ensure_ascii=False,separators=(',',':')))
    print('Archive ready:',len(cards),'races with place and QPL dividends',flush=True)

if __name__=='__main__':bootstrap()
