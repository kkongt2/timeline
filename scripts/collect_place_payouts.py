"""Official settled PLACE dividends are targets ONLY, never input features."""
import gzip, json, re, hashlib
from itertools import combinations
from pathlib import Path
CIRCLES={chr(0x2460+i):i+1 for i in range(20)}
VENUES={1:'seoul',2:'jeju',3:'busan'}

def payouts(block, winners):
    heading = re.search(r'배당률\s+단:', block)
    if not heading: raise ValueError('no dividend heading')
    match = re.search(r'\s연:\s*(.*?)\s+복:', block[heading.end():], re.S)
    if not match: raise ValueError('no place dividends')
    value=match[1].strip(); pattern=r'([①-⑳])\s*(\d+(?:\.\d+)?)';result={}
    for a,d in re.findall(pattern,value):
        key=str(CIRCLES[a])
        if key in result or float(d)<1:raise ValueError('invalid dividend')
        result[key]=float(d)
    if re.sub(pattern,'',value).strip():raise ValueError('unparsed place text')
    if set(result)!={str(n) for n in winners}:raise ValueError('Place winners disagree with official slots')
    return result

def run(root=Path('.')):
    history=[json.loads(x) for x in gzip.decompress((root/'training/history-v7.jsonl.gz').read_bytes()).splitlines()]
    index={(r['date'],r['venue'],r['race_no']):r for r in history}
    manifest=json.loads((root/'training/manifest.json').read_text()); out=[]; skipped=[]; missing=[]
    for report in manifest['reports']:
        path=root/'training/raw'/str(report['meet'])/(report['date']+'.txt.gz')
        if not path.exists(): missing.append(str(path));continue
        raw=gzip.decompress(path.read_bytes()); text=raw.decode()
        for block in re.split(r'(?=제목\s*:\s*\d{2,4}년)',text):
            m=re.search(r'제목\s*:\s*(\d{2,4})년\s*(\d+)월\s*(\d+)일.*?제\s*(\d+)경주',block)
            if not m:continue
            y,mo,d,rn=map(int,m.groups());y+=2000 if y<100 else 0
            date=f'{y:04d}{mo:02d}{d:02d}'
            if date!=report['date']:raise ValueError('date mismatch')
            key=(date,VENUES[report['meet']],rn);r=index.get(key)
            if not r:continue
            winners=r['place_winners']
            try:
                pp=payouts(block,winners)
                out.append(dict(date=date,venue=key[1],race_no=rn,payouts=pp,source=report['source'],source_sha256=hashlib.sha256(raw).hexdigest()))
            except ValueError as e:skipped.append(dict(date=date,venue=key[1],race_no=rn,reason=str(e)))
    quality=dict(reports=len(manifest['reports']),eligible_history=len(history),with_payouts=len(out),missing_reports=len(missing),exclusions=skipped)
    (root/'training/payout-quality.json').write_text(json.dumps(quality,ensure_ascii=False,indent=2))
    print({k:v for k,v in quality.items() if k!='exclusions'},flush=True)
    if missing:raise ValueError(f'{len(missing)} missing cached reports; never fill missing payouts with zero')
    if len(out)<10000:raise ValueError('Insufficient payout coverage')
    (root/'training/payouts.json.gz').write_bytes(gzip.compress(json.dumps(out,ensure_ascii=False,separators=(',',':')).encode(),mtime=0))

if __name__=='__main__':run()
