#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Collect today's KRA race cards from public KRA race pages.

No API key is required. The output is consumed by the static GitHub Pages app.
"""
from __future__ import annotations
import json, re, sys, time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

BASE = "https://race.kra.co.kr/chulmainfo"
MEETS = {
    1: ("seoul", "서울"),
    2: ("jeju", "제주"),
    3: ("busan", "부경"),
}
UA = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/131 Safari/537.36"
S = requests.Session()
S.headers.update({
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
    "Referer": "https://race.kra.co.kr/",
})

def clean(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

def fnum(v, default=0.0):
    m = re.search(r"-?\d+(?:\.\d+)?", clean(str(v)))
    return float(m.group()) if m else default

def inum(v, default=0):
    try:
        return int(round(fnum(v, default)))
    except Exception:
        return default

def get_html(endpoint: str, params: dict) -> str:
    url = f"{BASE}/{endpoint}"
    r = S.get(url, params=params, timeout=25)
    r.raise_for_status()
    # KRA legacy pages have historically used CP949/EUC-KR.
    for enc in (r.apparent_encoding, "cp949", "euc-kr", "utf-8"):
        if not enc:
            continue
        try:
            text = r.content.decode(enc, errors="strict")
            if "마명" in text or "출전" in text:
                return text
        except Exception:
            pass
    return r.content.decode("cp949", errors="ignore")

def params(date: str, rc_no: int, meet: int) -> dict:
    return {"meet": meet, "rcNo": rc_no, "rcDate": date, "Act": "02", "Sub": "1"}

def table_rows(table):
    out = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if not tds:
            continue
        row = [clean(td.get_text(" ", strip=True)) for td in tds]
        if row:
            out.append(row)
    return out

def table_headers(table):
    # Best-effort flattened labels; mainly used for diagnostics.
    hs = []
    for tr in table.find_all("tr"):
        ths = tr.find_all("th")
        if ths:
            vals = [clean(th.get_text(" ", strip=True)) for th in ths]
            if len(vals) > len(hs):
                hs = vals
    return hs

def find_card_table(soup):
    for t in soup.find_all("table"):
        txt = clean(t.get_text(" ", strip=True))
        if "마명" in txt and ("레이팅" in txt or "기수명" in txt) and ("중량" in txt or "부담" in txt):
            if len(table_rows(t)) >= 2:
                return t
    return None

def metadata(soup, expected_date, expected_rc):
    text = clean(soup.get_text(" ", strip=True))
    dm = re.search(r"(20\d{2})년\s*(\d{1,2})월\s*(\d{1,2})일", text)
    rm = re.search(r"제\s*(\d+)경주", text)
    got_date = f"{int(dm.group(1)):04d}{int(dm.group(2)):02d}{int(dm.group(3)):02d}" if dm else None
    got_rc = int(rm.group(1)) if rm else None
    if got_date and got_date != expected_date:
        return None
    if got_rc and got_rc != expected_rc:
        return None
    dist = re.search(r"\b(\d{3,4})M\b", text)
    tm = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", text)
    grade = None
    gm = re.search(r"(국\d등급|혼\d등급|제\d등급|\d등급|오픈)", text)
    if gm: grade = gm.group(1)
    return {
        "distance": int(dist.group(1)) if dist else None,
        "start_time": f"{int(tm.group(1)):02d}:{tm.group(2)}" if tm else None,
        "grade": grade,
    }

def parse_rating(s):
    return inum(s)

def parse_card(date: str, rc_no: int, meet: int):
    html = get_html("chulmaDetailInfoChulmapyo.do", params(date, rc_no, meet))
    soup = BeautifulSoup(html, "html.parser")
    meta = metadata(soup, date, rc_no)
    if meta is None:
        return None, {"reason": "metadata_mismatch"}
    table = find_card_table(soup)
    if table is None:
        return None, {"reason": "card_table_not_found"}
    rows = table_rows(table)
    horses = []
    for row in rows:
        # Current KRA card shape:
        # 번호, 마명, 마종/산지, 성별, 연령, 레이팅, 중량, 증감,
        # 기수명, 조교사명, 마주명, 조교횟수, 출전주기, 장구현황, 특이사항
        if len(row) < 9 or not re.fullmatch(r"\d+", row[0]):
            continue
        no = int(row[0])
        rating = parse_rating(row[5]) if len(row) > 5 else 0
        burden = fnum(row[6]) if len(row) > 6 else 0
        jockey = row[8] if len(row) > 8 else ""
        trainer = row[9] if len(row) > 9 else ""
        training = inum(row[11]) if len(row) > 11 else 0
        interval = inum(row[12]) if len(row) > 12 else 0
        note = row[14] if len(row) > 14 else ""
        # Exclude explicit cancelled/withdrawn rows.
        if any(x in note for x in ("출전취소", "출전제외", "경주취소")):
            continue
        horses.append({
            "number": no,
            "name": row[1],
            "rating": rating,
            "burden": burden,
            "burden_change": fnum(row[7]) if len(row) > 7 else 0,
            "jockey": jockey,
            "trainer": trainer,
            "training_count": training,
            "interval_weeks": interval,
            "gear": row[13] if len(row) > 13 else "",
            "note": note,
            # Filled by enrichment pages when available.
            "starts_1y": 0, "wins_1y": 0, "seconds_1y": 0, "thirds_1y": 0,
            "distance_starts": 0, "distance_top3": 0,
            "recent_finishes": [],
        })
    if len(horses) < 2:
        return None, {"reason": "too_few_horses", "headers": table_headers(table), "rows": rows[:3]}
    race = {
        "venue": MEETS[meet][0],
        "venue_name": MEETS[meet][1],
        "date": date,
        "race_no": rc_no,
        "distance": meta["distance"],
        "start_time": meta["start_time"],
        "grade": meta["grade"],
        "title": " · ".join(x for x in [meta["grade"], f'{meta["distance"]}M' if meta["distance"] else None, meta["start_time"]] if x),
        "horses": horses,
        "source": "KRA public race page",
    }
    return race, {"headers": table_headers(table), "first_row": rows[0] if rows else []}

def match_horse(row, by_name, by_no):
    for cell in row[:3]:
        c = clean(cell)
        if c in by_name:
            return by_name[c]
    if row and re.fullmatch(r"\d+", row[0]) and int(row[0]) in by_no:
        return by_no[int(row[0])]
    return None

def enrich_record(race, date, rc_no, meet, debug):
    try:
        html = get_html("chulmaDetailInfoRecord.do", params(date, rc_no, meet))
        soup = BeautifulSoup(html, "html.parser")
        by_name = {h["name"]: h for h in race["horses"]}
        by_no = {h["number"]: h for h in race["horses"]}
        samples = []
        for t in soup.find_all("table"):
            rows = table_rows(t)
            if not rows: continue
            head = clean(t.get_text(" ", strip=True))[:300]
            if "전적" not in head and "승률" not in head and "복승률" not in head:
                continue
            if len(samples) < 2:
                samples.append({"headers": table_headers(t), "rows": rows[:3]})
            for row in rows:
                h = match_horse(row, by_name, by_no)
                if not h: continue
                # Parse compact forms such as 12(3/2) = starts(wins/seconds).
                compact = []
                for cell in row:
                    m = re.search(r"(\d+)\s*\(\s*(\d+)\s*/\s*(\d+)\s*\)", cell)
                    if m:
                        compact.append(tuple(map(int, m.groups())))
                if compact:
                    starts, wins, seconds = compact[-1]  # usually recent/1-year block is last
                    if starts >= wins + seconds:
                        h["starts_1y"], h["wins_1y"], h["seconds_1y"] = starts, wins, seconds
                # Some table variants expose W/S/T in separate cells; top3 rate is recovered later.
        debug["record_samples"] = samples
    except Exception as e:
        debug["record_error"] = repr(e)

def enrich_distance(race, date, rc_no, meet, debug):
    try:
        html = get_html("chulmaDetailInfoDistanceRecord.do", params(date, rc_no, meet))
        soup = BeautifulSoup(html, "html.parser")
        by_name = {h["name"]: h for h in race["horses"]}
        by_no = {h["number"]: h for h in race["horses"]}
        samples = []
        for t in soup.find_all("table"):
            rows = table_rows(t)
            if not rows: continue
            txt = clean(t.get_text(" ", strip=True))
            if "거리" not in txt and "전적" not in txt:
                continue
            if len(samples) < 2:
                samples.append({"headers": table_headers(t), "rows": rows[:3]})
            for row in rows:
                h = match_horse(row, by_name, by_no)
                if not h: continue
                compact = []
                for cell in row:
                    m = re.search(r"(\d+)\s*\(\s*(\d+)\s*/\s*(\d+)\s*\)", cell)
                    if m: compact.append(tuple(map(int, m.groups())))
                if compact:
                    starts, wins, seconds = compact[0]
                    h["distance_starts"] = starts
                    h["distance_top3"] = min(starts, wins + seconds)
        debug["distance_samples"] = samples
    except Exception as e:
        debug["distance_error"] = repr(e)

def enrich_recent(race, date, rc_no, meet, debug):
    try:
        html = get_html("chulmaDetailInfo10Score.do", params(date, rc_no, meet))
        soup = BeautifulSoup(html, "html.parser")
        by_name = {h["name"]: h for h in race["horses"]}
        samples = []
        for t in soup.find_all("table"):
            txt = clean(t.get_text(" ", strip=True))
            h = next((v for n,v in by_name.items() if n and n in txt[:180]), None)
            rows = table_rows(t)
            if not h or not rows: continue
            finishes = []
            for row in rows:
                # Historical rows contain an ordinal column. Prefer a standalone 1..20 value
                # after date-like cells and avoid gate numbers where possible.
                vals = [inum(c, -1) for c in row]
                candidates = [v for v in vals[1:8] if 1 <= v <= 20]
                if candidates:
                    finishes.append(candidates[-1])
            if finishes:
                h["recent_finishes"] = finishes[:5]
                if len(samples) < 2:
                    samples.append({"horse": h["name"], "rows": rows[:2], "finishes": h["recent_finishes"]})
        debug["recent_samples"] = samples
    except Exception as e:
        debug["recent_error"] = repr(e)

def main():
    kst = ZoneInfo("Asia/Seoul")
    now = datetime.now(kst)
    # Race cards are published before the meeting; keep today plus the next 2 days
    # so Fri/Sat/Sun can be selected from the mobile UI.
    dates = [(now + timedelta(days=i)).strftime("%Y%m%d") for i in range(3)]
    races, errors, debug_race = [], [], None
    for date in dates:
        for meet in MEETS:
            misses = 0
            for rc_no in range(1, 17):
                try:
                    race, dbg = parse_card(date, rc_no, meet)
                    if not race:
                        misses += 1
                        # After several consecutive missing races, higher race numbers won't exist.
                        if misses >= 3 and rc_no >= 4:
                            break
                        continue
                    misses = 0
                    enrich_record(race, date, rc_no, meet, dbg)
                    enrich_distance(race, date, rc_no, meet, dbg)
                    enrich_recent(race, date, rc_no, meet, dbg)
                    races.append(race)
                    if debug_race is None:
                        debug_race = {"date":date,"meet":meet,"rc_no":rc_no,**dbg}
                    print(f"OK {date} meet={meet} race={rc_no} horses={len(race['horses'])}")
                    time.sleep(0.12)
                except Exception as e:
                    errors.append({"date":date,"meet":meet,"race_no":rc_no,"error":repr(e)})
                    print(f"ERR {date} meet={meet} race={rc_no}: {e}", file=sys.stderr)
                    time.sleep(0.3)
    out = {
        "updated_at": now.isoformat(timespec="seconds"),
        "races": races,
        "status": {
            "race_count": len(races),
            "error_count": len(errors),
            "dates": dates,
            "note": "Auto-collected from KRA public race pages; odds may require manual entry.",
        },
    }
    Path("data").mkdir(exist_ok=True)
    Path("data/latest.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    Path("data/debug.json").write_text(json.dumps({
        "updated_at": now.isoformat(timespec="seconds"),
        "errors": errors[:50],
        "sample": debug_race,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(races)} races; errors={len(errors)}")
    # Do not fail the workflow just because there is no racing today.
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
