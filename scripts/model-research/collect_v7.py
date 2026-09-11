"""Reparse official cached reports for pre-race history, never betting inputs."""
import gzip
import json
import re
from pathlib import Path
from collect import get, VENUES, CIRCLES


def parse_report(text, meet, expected):
    out, issues = [], []
    for block in re.split(r'(?=제목\s*:\s*\d{2,4}년)', text):
        m = re.search(r'제목\s*:\s*(\d{2,4})년\s*(\d+)월\s*(\d+)일.*?제\s*(\d+)경주', block)
        if not m:
            continue
        y, month, day, rn = map(int, m.groups()); y += 2000 if y < 100 else 0
        date = f'{y:04d}{month:02d}{day:02d}'
        if date != expected:
            raise ValueError('Report date mismatch')
        dist = re.search(r'제\s*\d+일\s+(\d+)M', block)
        grade = re.search(r'(국\d등급|혼\d등급|제\d등급|\d등급|오픈)', block)
        hs = {}; section = None; ambiguous = False
        for line in block.splitlines():
            if '순위' in line and '마번' in line:
                section = 'card' if '부담중량' in line else ('weight' if '마체중' in line.replace(' ', '') else ('sectionals' if 'G-1F' in line else 'other'))
                continue
            if section == 'card':
                h = re.match(r'^\s*(\S+)\s+(\d+)\s+(\S+)\s+(\S+)\s+([암수거])\s+(\d+)\s+([\d.]+)\s+(\S+)\s+(\S+)\s+(.*)$', line)
                if h:
                    pos, no, name, origin, sex, age, burden, jockey, trainer, tail = h.groups()
                    if pos in ('취소', '제외'): continue
                    if not pos.isdigit() and pos not in ('중지', '실격'): ambiguous = True; continue
                    rt = re.search(r'\s+(\d+)\s*$', tail)
                    hs[int(no)] = dict(number=int(no), name=name, finish=int(pos) if pos.isdigit() else None,
                        finish_status=pos if not pos.isdigit() else 'finished', age=int(age), sex=sex,
                        rating=int(rt[1]) if rt else 0, burden=float(burden), jockey=re.sub(r'^\([^)]*\)', '', jockey), trainer=trainer)
                elif re.match(r'^\s*\S+\s+\d+\s+\S+', line): ambiguous = True
            elif section == 'weight':
                h = re.match(r'^\s*\S+\s+(\d+)\s+\S+\s+(\d+)(?:\(\s*([+-]?\d+)\)|([+-]\d+))?\s+(\d+):(\d+\.\d+)', line)
                if h and int(h[1]) in hs:
                    horse=hs[int(h[1])];horse.update(horse_weight=int(h[2]),horse_weight_change=int(h[3] or h[4] or 0),race_seconds=60*int(h[5])+float(h[6]))
                    positions=re.search(r'(\d+\s*(?:-\s*\d*\s*){5,6})$',line)
                    if positions:
                        parts=re.split(r'\s*-\s*',positions[1].strip())
                        if parts[0] and parts[-1]:horse.update(early_position=int(parts[0]),last_position=int(parts[-1]))
            elif section == 'sectionals':
                cells=line.split()
                def seconds(value):
                    return sum(float(v)*factor for v,factor in zip(value.split(':')[::-1],[1,60]))
                if len(cells)>=7 and cells[0].isdigit() and cells[1].isdigit() and int(cells[1]) in hs:
                    try:
                        early,last=seconds(cells[3]),seconds(cells[-3])
                        if 8<=early<=40 and 8<=last<=40:hs[int(cells[1])].update(early_seconds=early,last_seconds=last)
                    except ValueError:pass
        pp = re.search(r'배당률\s+단:.*?\s연:\s*(.*?)\s+복:', block, re.S)
        winners = [CIRCLES[c] for c in pp[1] if c in CIRCLES] if pp else []
        n = len(hs); ordered = sorted(hs.values(), key=lambda h: h['finish'] if h['finish'] is not None else 99)
        finishers = [h for h in ordered if h['finish'] is not None]
        positions = [h['finish'] for h in finishers]
        # Retain known DNF/DQ losers only when official winners and the entire field are unambiguous.
        valid = (not ambiguous and dist and 3 <= n <= 16 and len(finishers) >= 3
                 and positions == list(range(1, len(positions)+1)) and len(winners) in (2, 3)
                 and winners == [h['number'] for h in finishers[:len(winners)]])
        if not valid:
            issues.append({'date': date, 'venue': VENUES[meet], 'race_no': rn, 'reason': 'ambiguous_field_or_official_winners'})
            continue
        for h in ordered:
            if h['finish'] is None: h['finish'] = n+1
        tr = re.search(r'주로:\s*(\S+)', block)
        out.append(dict(date=date, venue=VENUES[meet], race_no=rn, distance=int(dist[1]),
            grade=grade[1] if grade else None, track_condition=tr[1] if tr else None,
            place_k=len(winners), place_winners=winners, horses=ordered))
    return out, issues


def run():
    manifest = json.loads(Path('training/manifest.json').read_text()); rows = []; issues = []; errors = []
    for i, report in enumerate(manifest['reports']):
        try:
            path = Path('training/raw') / str(report['meet']) / (report['date']+'.txt.gz')
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(gzip.compress(get(report['source']).encode(), mtime=0))
            text = gzip.decompress(path.read_bytes()).decode()
            result, skipped = parse_report(text, report['meet'], report['date'])
            rows.extend(result); issues.extend(skipped)
        except Exception as exc: errors.append({'source': report['source'], 'error': str(exc)})
        if i % 100 == 0: print('reparsed', i+1, 'races', len(rows), 'errors', len(errors), flush=True)
    quality = dict(races=len(rows), reports=len(manifest['reports']), errors=errors, exclusions=issues,
        early_positions=sum('early_position' in h for r in rows for h in r['horses']),
        sectionals=sum('early_seconds' in h for r in rows for h in r['horses']),
        nonfinishers=sum(h.get('finish_status') in ('中止','중지','실격') for r in rows for h in r['horses']))
    Path('training/quality-v7.json').write_text(json.dumps(quality, ensure_ascii=False, indent=2))
    if errors or len(rows) < 12000: raise ValueError('Incomplete historical enrichment')
    raw = ''.join(json.dumps(r, ensure_ascii=False, separators=(',', ':'))+'\n' for r in rows).encode()
    Path('training/history-v7.jsonl.gz').write_bytes(gzip.compress(raw, mtime=0))
    print({k:v for k,v in quality.items() if k not in ('exclusions','errors')}, flush=True)


if __name__ == '__main__': run()
