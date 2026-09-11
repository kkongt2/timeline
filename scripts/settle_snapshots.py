"""Recover results for saved forecasts even after cards leave the two-day window."""
import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from results_kra import attach_results
from update_kra import S, decode_response


def run():
    now=datetime.now(ZoneInfo('Asia/Seoul'));live=json.loads(Path('data/latest.json').read_text())
    available={(r['date'],r['venue'],r['race_no']):r.get('official_result') for r in live['races']}
    out=Path('data/settlements');out.mkdir(parents=True,exist_ok=True)
    for p in sorted(Path('data/predictions').glob('*.json')):
        target=out/p.name;results=json.loads(target.read_text()) if target.exists() else {};missing=[]
        for key,snapshot in json.loads(p.read_text())['races'].items():
            if results.get(key,{}).get('status')=='confirmed' and results[key].get('starters'):continue
            r=snapshot['input'];result=available.get((r['date'],r['venue'],r['race_no']))
            if result:results[key]=result
            elif datetime.fromisoformat(snapshot['start_at'])<now:missing.append(dict(r))
        if missing:
            attach_results(missing,{},now,S,decode_response)
            for r in missing:
                if r.get('official_result'):results[f"{r['date']}:{r['venue']}:{r['race_no']}"]=r['official_result']
        target.write_text(json.dumps(results,ensure_ascii=False,indent=2))


if __name__=='__main__':run()
