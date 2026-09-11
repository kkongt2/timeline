"""Download public daily KRA reports; validate dates, starters and payout winners."""
import argparse, gzip, hashlib, json, re, time, threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from urllib.parse import urljoin,parse_qs,urlparse
import requests
from bs4 import BeautifulSoup
BASE='https://race.kra.co.kr'
HEADERS={'User-Agent':'Mozilla/5.0','Referer':BASE+'/','Accept-Language':'ko-KR,ko;q=0.9'}
VENUES={1:'seoul',2:'jeju',3:'busan'}
CIRCLES={chr(0x2460+i):i+1 for i in range(20)}

RATE_LOCK=threading.Lock()
NEXT_REQUEST=0.0
LOCAL=threading.local()
def get(url,params=None):
 global NEXT_REQUEST
 if not hasattr(LOCAL,'session'):LOCAL.session=requests.Session()
 for attempt in range(3):
  try:
   with RATE_LOCK:
    time.sleep(max(0,NEXT_REQUEST-time.monotonic()));NEXT_REQUEST=time.monotonic()+1.0
   r=LOCAL.session.get(url,params=params,headers=HEADERS,timeout=(15,35));r.raise_for_status()
   for enc in ['cp949','utf-8',r.apparent_encoding]:
    try:return r.content.decode(enc)
    except (UnicodeError,TypeError):pass
   raise ValueError('Unknown text encoding')
  except (requests.RequestException,ValueError):
   if attempt==2:raise
   time.sleep(4*(attempt+1))

def catalog(args):
 meet,month=args;urls=set()
 for page in range(1,4):
  cache=Path('training/raw/catalog')/f'{meet}-{month}-{page}.txt.gz';cache.parent.mkdir(parents=True,exist_ok=True)
  if cache.exists():txt=gzip.decompress(cache.read_bytes()).decode('utf-8')
  else:
   txt=get(BASE+'/dbdata/textDataList.do',{'meet':meet,'fileType':'dacom11','fileSearchName':month,'pageIndex':page});cache.write_bytes(gzip.compress(txt.encode('utf-8'),mtime=0))
  soup=BeautifulSoup(txt,'html.parser');added=0
  for a in soup.select('a[href]'):
   href=a['href']
   if '/dbdata/fileDownLoad.do?' not in href:continue
   fn=parse_qs(urlparse(href).query).get('fn',[''])[0]
   m=re.search(r'(20\d{6})[^/]*\.(?:rpt|txt)$',fn)
   if m and m[1].startswith(month) and urljoin(BASE,href) not in urls:
    urls.add(urljoin(BASE,href));added+=1
  if not added:break
 return [(meet,u) for u in urls]

def parse_report(text,meet,expected):
 blocks=re.split(r'(?=제목\s*:\s*\d{2,4}년)',text);out=[];skips=[]
 for block in blocks:
  m=re.search(r'제목\s*:\s*(\d{2,4})년\s*(\d+)월\s*(\d+)일.*?제\s*(\d+)경주',block)
  if not m:continue
  y,mo,d,rn=map(int,m.groups());y=y+2000 if y<100 else y;dt=f'{y:04d}{mo:02d}{d:02d}'
  if dt!=expected:raise ValueError('Report date mismatch')
  dist=re.search(r'제\s*\d+일\s+(\d+)M',block)
  if not dist:skips.append([rn,'distance']);continue
  hs={};section=None;ambiguous=False
  for line in block.splitlines():
   if '순위' in line and '마번' in line:
    section='card' if '부담중량' in line else ('weight' if '마 체 중' in line else 'other');continue
   if section=='card':
    match=re.match(r'^\s*(\d+)\s+(\d+)\s+(\S+)\s+(\S+)\s+([암수거])\s+(\d+)\s+([\d.]+)\s+(\S+)\s+(\S+)\s+(.*)$',line)
    if match:
     pos,no,name,origin,sex,age,burden,jockey,trainer,tail=match.groups();rt=re.search(r'\s+(\d+)\s*$',tail)
     hs[int(no)]={'number':int(no),'name':name,'finish':int(pos),'burden':float(burden),'rating':int(rt[1]) if rt else 0,'jockey':re.sub(r'^\([^)]*\)','',jockey),'trainer':trainer,'age':int(age),'sex':sex,'horse_weight':None,'horse_weight_change':None}
    elif re.match(r'^\s*\S+\s+\d+\s+\S+',line) and not line.strip().startswith('순위'):
     # Never silently remove a DNF, DQ, or unparsed starter from a field.
     ambiguous=True
   elif section=='weight':
    wm=re.match(r'^\s*\d+\s+(\d+)\s+\S+\s+(\d+)\(\s*([+-]?\d+)\)',line)
    if wm and int(wm[1]) in hs:
     hs[int(wm[1])].update(horse_weight=int(wm[2]),horse_weight_change=int(wm[3]))
     tm=re.search(r'\)\s+(\d+):(\d+\.\d+)',line)
     if tm:hs[int(wm[1])]['race_seconds']=60*int(tm[1])+float(tm[2])
  pp=re.search(r'배당률\s+단:.*?\s연:\s*(.*?)\s+복:',block)
  winners=[CIRCLES[c] for c in pp[1] if c in CIRCLES] if pp else []
  order=sorted(hs.values(),key=lambda h:h['finish']);positions=[h['finish'] for h in order]
  if ambiguous or not 3<=len(hs)<=16 or positions!=list(range(1,len(hs)+1)) or len(winners) not in (2,3) or winners!=[h['number'] for h in order[:len(winners)]]:
   skips.append([rn,'ambiguous_field_or_payout']);continue
  out.append({'date':dt,'venue':VENUES[meet],'race_no':rn,'distance':int(dist[1]),'place_k':len(winners),'track_condition':(re.search(r'주로:\s*(\S+)',block)[1] if re.search(r'주로:\s*(\S+)',block) else None),'horses':order})
 return out,skips

def download(args):
 meet,url=args;fn=parse_qs(urlparse(url).query)['fn'][0];dt=re.search(r'(20\d{6})[^/]*\.(?:rpt|txt)$',fn)[1]
 cache=Path('training/raw')/str(meet)/(dt+'.txt.gz');cache.parent.mkdir(parents=True,exist_ok=True)
 if cache.exists():txt=gzip.decompress(cache.read_bytes()).decode('utf-8')
 else:txt=get(url);cache.write_bytes(gzip.compress(txt.encode('utf-8'),mtime=0))
 races,skips=parse_report(txt,meet,dt)
 return {'source':url,'date':dt,'meet':meet,'sha256':hashlib.sha256(txt.encode()).hexdigest(),'races':races,'skips':skips}

def run(end,start='20210101'):
 jobs=[(v,f'{y}{m:02d}') for v in VENUES for y in range(int(start[:4]),int(end[:4])+1) for m in range(1,13) if start[:6]<=f'{y}{m:02d}'<=end[:6]]
 urls=[];errors=[]
 with ThreadPoolExecutor(max_workers=2) as ex:
  for job,result in zip(jobs,ex.map(catalog,jobs)):
   urls.extend(result);print('catalog',job,'reports',len(result),flush=True)
 urls=sorted(set((v,u) for v,u in urls if start<=re.search(r'(20\d{6})[^/]*\.(?:rpt|txt)',u)[1]<=end))
 print('daily_reports',len(urls),flush=True);out={};manifest=[]
 def safe(job):
  try:return download(job)
  except Exception as e:return {'source':job[1],'error':str(e)}
 with ThreadPoolExecutor(max_workers=2) as ex:
  for i,res in enumerate(ex.map(safe,urls)):
   if 'error' in res:errors.append(res)
   else:
    for r in res.pop('races'):out[(r['date'],r['venue'],r['race_no'])]=r
    manifest.append(res)
   if (i+1)%25==0:print('collected',i+1,'/',len(urls),'races',len(out),'errors',len(errors),flush=True)
 Path('training').mkdir(exist_ok=True);p=Path('training/history.jsonl');p.write_text(''.join(json.dumps(out[k],ensure_ascii=False)+'\n' for k in sorted(out)),encoding='utf-8');Path('training/manifest.json').write_text(json.dumps({'reports':manifest,'errors':errors,'races':len(out)},ensure_ascii=False))
 print('total',len(out),'by_venue',{v:sum(r['venue']==v for r in out.values()) for v in VENUES.values()},flush=True)
 if len(errors)>len(urls)*.02:raise ValueError('Too many missing daily reports')
 if len(out)<3000:raise ValueError('Fewer than 3000 validated races')

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--end',default='20260910');p.add_argument('--start',default='20210101');a=p.parse_args();run(a.end,a.start)
