"""Incrementally refresh completed dates using the same report parser and features."""
import gzip,json,re
from collections import defaultdict
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from collect import catalog,get,VENUES
from collect_v7 import parse_report
from features_v7 import History,attach

def refresh_and_attach(races):
    path=Path('data/history-context-v7.json.gz')
    if not path.exists():return {'status':'missing'}
    context=json.loads(gzip.decompress(path.read_bytes()));store=History(context)
    now=datetime.now(ZoneInfo('Asia/Seoul'));end=(now-timedelta(days=1)).strftime('%Y%m%d')
    status={'status':'ready','through':store.through,'added_races':0}
    try:
        if store.through<end:
            first=datetime.strptime(store.through,'%Y%m%d')+timedelta(days=1)
            if (now.replace(tzinfo=None)-first).days>14:raise ValueError('History requires full refresh')
            months=set();d=first
            while d.strftime('%Y%m%d')<=end:months.add(d.strftime('%Y%m'));d+=timedelta(days=1)
            jobs=[]
            for meet in VENUES:
                for month in sorted(months):
                    for p in Path('training/raw/catalog').glob(f'{meet}-{month}-*.txt.gz'):p.unlink()
                    for v,url in catalog((meet,month)):
                        match=re.search(r'(20\d{6})[^/]*\.(?:rpt|txt)',url)
                        if match and store.through<match[1]<=end:jobs.append((v,url,match[1]))
            byday=defaultdict(list)
            for meet,url,date in sorted(set(jobs)):
                p=Path('training/raw')/str(meet)/(date+'.txt.gz')
                text=gzip.decompress(p.read_bytes()).decode() if p.exists() else get(url)
                rows,_=parse_report(text,meet,date)
                for r in rows:
                    if r['place_k']==(2 if len(r['horses'])<=7 else 3):byday[date].append(r)
            for date in sorted(byday):store.add_day(byday[date]);status['added_races']+=len(byday[date])
            context=store.export();status['through']=store.through
    except Exception as exc:status.update(status='refresh_failed',error=str(exc))
    attach(races,context)
    path.write_bytes(gzip.compress(json.dumps(context,ensure_ascii=False,separators=(',',':')).encode(),mtime=0))
    return status
