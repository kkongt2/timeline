"""Keep official report odds separate from settled payouts and model inputs."""
import gzip,json,math,re,sys
from pathlib import Path

def parse_place_quotes(block):
    quotes={};active=False
    for line in block.splitlines():
        if '마번' in line and '단승식' in line and '연승식' in line:
            active=True;continue
        if not active:continue
        if line.lstrip().startswith('(') or '배당률 단:' in line:break
        cells=line.split()
        if len(cells)<4 or not cells[1].isdigit():continue
        if not (cells[0].isdigit() or cells[0] in ('중지','실격')):continue
        try:number=int(cells[1]);odds=float(cells[-1])
        except ValueError:continue
        if not 1<=number<=20 or not math.isfinite(odds) or odds<1:continue
        if number in quotes:raise ValueError('Duplicate horse in report odds')
        quotes[number]=dict(numbers=[number],odds=odds)
    return list(quotes.values())

def parse_report(text,date):
    races={}
    for block in re.split(r'(?=제목\s*:\s*\d{2,4}년)',text):
        m=re.search(r'제목\s*:\s*(\d{2,4})년\s*(\d+)월\s*(\d+)일.*?제\s*(\d+)경주',block)
        if not m:continue
        y,mo,d,rn=map(int,m.groups());y+=2000 if y<100 else 0
        if f'{y:04d}{mo:02d}{d:02d}'!=date:raise ValueError('Odds report date mismatch')
        races[rn]=dict(place=dict(quotes=parse_place_quotes(block)),pair=dict(quotes=[],status='unavailable'))
    return races

def run():
    sys.path.insert(0,str(Path(__file__).parent/'model-research'))
    from collect import get,catalog
    meets={'seoul':1,'jeju':2,'busan':3};directory=Path('data/market-odds');directory.mkdir(parents=True,exist_ok=True)
    catalogs={};count=0;errors=[]
    for path in sorted(Path('data/calendar').glob('????????.json')):
        doc=json.loads(path.read_text(encoding='utf-8'));date=doc['date'];target=directory/path.name
        out=json.loads(target.read_text(encoding='utf-8')) if target.exists() else dict(schema=1,date=date,races={})
        for venue in sorted({r['venue'] for r in doc['races']}):
            cards=[r for r in doc['races'] if r['venue']==venue and r.get('official_result',{}).get('status')=='confirmed']
            if not cards or all(out['races'].get(f'{venue}:{r["race_no"]}',{}).get('place',{}).get('quotes') for r in cards):continue
            meet=meets[venue];cache=Path('training/raw')/str(meet)/(date+'.txt.gz')
            try:
                source=next((r['official_result']['source'] for r in cards if 'fileDownLoad.do' in r['official_result'].get('source','')),None)
                if not cache.exists():
                    if not source:
                        key=(meet,date[:6])
                        if key not in catalogs:
                            # Training caches stop at the original collection date.
                            # Refresh a missing report's month before declaring it absent.
                            for listing in Path('training/raw/catalog').glob(f'{meet}-{date[:6]}-*.txt.gz'):listing.unlink()
                            catalogs[key]=catalog(key)
                        source=next((url for _,url in catalogs[key] if re.search(r'(20\d{6})[^/]*\.(?:rpt|txt)',url)[1]==date),None)
                    if not source:raise ValueError('Daily report not available yet')
                    cache.parent.mkdir(parents=True,exist_ok=True);cache.write_bytes(gzip.compress(get(source).encode('utf-8'),mtime=0))
                parsed=parse_report(gzip.decompress(cache.read_bytes()).decode('utf-8'),date)
                for r in cards:
                    if r['race_no'] not in parsed:continue
                    markets=parsed[r['race_no']];starters=r['official_result'].get('starters') or [h['number'] for h in r['horses']]
                    markets['place']['quotes']=[q for q in markets['place']['quotes'] if q['numbers'][0] in starters]
                    markets['source']=source or r['official_result'].get('source')
                    out['races'][f'{venue}:{r["race_no"]}']=markets;count+=1
            except Exception as exc:
                errors.append(dict(date=date,venue=venue,error=str(exc)));print('Odds unavailable:',date,venue,str(exc),flush=True)
        target.write_text(json.dumps(out,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print('Report odds updated:',count,'races; errors:',len(errors),flush=True)
    Path('data/market-odds-status.json').write_text(json.dumps(dict(schema=1,updated_races=count,errors=errors),ensure_ascii=False),encoding='utf-8')

if __name__=='__main__':run()
