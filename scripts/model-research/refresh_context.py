"""Refresh only completed prior dates, then construct the same features as training."""
import json
import re
from collections import defaultdict
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from collect import catalog,download,VENUES
from features_v6 import History,attach,validate_rows

def refresh_and_attach(races):
 path=Path('data/history-context.json')
 if not path.exists():return {'status':'missing'}
 context=json.loads(path.read_text());store=History(context)
 today=datetime.now(ZoneInfo('Asia/Seoul'));end=(today-timedelta(days=1)).strftime('%Y%m%d')
 status={'status':'ready','through':context['through'],'added_races':0}
 try:
  if context['through']<end:
   first=datetime.strptime(context['through'],'%Y%m%d')+timedelta(days=1)
   if (today.replace(tzinfo=None)-first).days>14:raise ValueError('History is more than 14 days behind; full refresh required')
   months=set();d=first
   while d.strftime('%Y%m%d')<=end:months.add(d.strftime('%Y%m'));d+=timedelta(days=1)
   jobs=[]
   for meet in VENUES:
    for month in sorted(months):
     # Today's list can gain yesterday's report; do not retain a negative catalog cache.
     for p in Path('training/raw/catalog').glob(f'{meet}-{month}-*.txt.gz'):p.unlink()
     for v,url in catalog((meet,month)):
      match=re.search(r'(20\d{6})[^/]*\.(?:rpt|txt)',url)
      if match and context['through']<match[1]<=end:jobs.append((v,url))
   rows=[]
   for job in sorted(set(jobs)):
    result=download(job);rows.extend(result['races'])
   rows,issues=validate_rows(rows);byday=defaultdict(list)
   for r in rows:byday[r['date']].append(r)
   for day in sorted(byday):store.add_day(byday[day])
   if rows:
    context=store.export();tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(context,ensure_ascii=False,separators=(',',':')));tmp.replace(path)
   status.update(through=context['through'],added_races=len(rows),excluded=len(issues))
 except Exception as e:status.update(status='refresh_failed',error=str(e))
 attach(races,context)
 return status
