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
    last = None
    for attempt in range(3):
        try:
            r = S.get(url, params=params, timeout=(10, 25))
            r.raise_for_status()
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
        except requests.RequestException as e:
            last = e
            time.sleep(0.8 * (attempt + 1))
    raise last

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
            "age": inum(row[4]), "sex": row[3],
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
    for tr in table.select('tr'):
        cells=tr.find_all('td')
        if len(cells)<2: continue
        number=inum(cells[0].get_text())
        match=re.search(r"(?:hrNo[=\s'\":]+|(?:goHorse|goPage1)\(\s*['\"]?)([0-9]+)", str(cells[1]))
        if match:
            for horse in horses:
                if horse['number']==number: horse['horse_id']=match[1]
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

STATIC_HORSE_FIELDS = (
    "starts_1y","wins_1y","seconds_1y","thirds_1y",
    "distance_starts","distance_top3","recent_finishes",
)

def reuse_static_horse_data(race, previous):
    if not previous:
        return False
    old = {h.get("name"): h for h in previous.get("horses", []) if h.get("name")}
    if not old:
        return False
    matched = 0
    for h in race.get("horses", []):
        p = old.get(h.get("name"))
        if not p:
            continue
        matched += 1
        for key in STATIC_HORSE_FIELDS:
            if key in p:
                h[key] = p[key]
    # Only skip the historical sub-pages when essentially the same field is present.
    return matched >= max(2, len(race.get("horses", [])) - 1)

def enrich_record(race, date, rc_no, meet, debug):
    try:
        html = get_html("chulmaDetailInfoRecord.do", params(date, rc_no, meet))
        soup = BeautifulSoup(html, "html.parser")
        by_name = {h["name"]: h for h in race["horses"]}
        by_no = {h["number"]: h for h in race["horses"]}
        samples = []
        for t in soup.find_all("table"):
            rows = table_rows(t)
            if not rows:
                continue
            head = clean(t.get_text(" ", strip=True))[:300]
            if "전적" not in head and "승률" not in head and "복승률" not in head:
                continue
            if len(samples) < 2:
                samples.append({"headers": table_headers(t), "rows": rows[:3]})
            for row in rows:
                h = match_horse(row, by_name, by_no)
                if not h:
                    continue
                # Current KRA compact form: starts(wins/seconds/thirds), e.g. 12(3/2/1).
                compact = []
                for cell in row:
                    m = re.search(r"(\d+)\s*\(\s*(\d+)\s*/\s*(\d+)\s*/\s*(\d+)\s*\)", cell)
                    if m:
                        compact.append(tuple(map(int, m.groups())))
                if compact:
                    # The record page currently exposes two blocks. Use the latter,
                    # which is the recent-period block on the live page.
                    starts, wins, seconds, thirds = compact[-1]
                    if starts >= wins + seconds + thirds:
                        h["starts_1y"] = starts
                        h["wins_1y"] = wins
                        h["seconds_1y"] = seconds
                        h["thirds_1y"] = thirds
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
            if not rows:
                continue
            txt = clean(t.get_text(" ", strip=True))
            if "거리" not in txt and "전적" not in txt:
                continue
            if len(samples) < 2:
                samples.append({"headers": table_headers(t), "rows": rows[:3]})
            for row in rows:
                h = match_horse(row, by_name, by_no)
                if not h:
                    continue
                compact = []
                for cell in row:
                    m = re.search(r"(\d+)\s*\(\s*(\d+)\s*/\s*(\d+)\s*/\s*(\d+)\s*\)", cell)
                    if m:
                        compact.append(tuple(map(int, m.groups())))
                if compact:
                    starts, wins, seconds, thirds = compact[0]
                    h["distance_starts"] = starts
                    h["distance_top3"] = min(starts, wins + seconds + thirds)
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
            h = next((v for n, v in by_name.items() if n and n in txt[:180]), None)
            rows = table_rows(t)
            if not h or not rows:
                continue
            finishes = []
            for row in rows:
                # Current recent-race table exposes finish/field-size as "8/10".
                # This avoids mistaking age, distance, gate, etc. for finish position.
                finish = None
                for cell in row:
                    m = re.fullmatch(r"\s*(\d{1,2})\s*/\s*(\d{1,2})\s*", cell)
                    if m:
                        pos, field_size = map(int, m.groups())
                        if 1 <= pos <= field_size <= 20:
                            finish = pos
                            break
                if finish is not None:
                    finishes.append(finish)
            if finishes:
                h["recent_finishes"] = finishes[:5]
                if len(samples) < 2:
                    samples.append({
                        "horse": h["name"],
                        "rows": rows[:2],
                        "finishes": h["recent_finishes"],
                    })
        debug["recent_samples"] = samples
    except Exception as e:
        debug["recent_error"] = repr(e)


def decode_response(r):
    for enc in (r.apparent_encoding, "cp949", "euc-kr", "utf-8"):
        if not enc:
            continue
        try:
            return r.content.decode(enc, errors="strict")
        except Exception:
            pass
    return r.content.decode("utf-8", errors="ignore")

def norm_person_name(name):
    # Apprentice allowance is sometimes rendered as "(-1)우인철".
    return re.sub(r"^\([^)]*\)\s*", "", clean(name))

def fetch_person_stats(kind, meet):
    if kind == "jockey":
        url = "https://race.kra.co.kr/jockey/RankScoreYearCompare.do"
        qs = {"Act":"08","Sub":"2","meet":meet}
        key = "기수명"
    else:
        url = "https://race.kra.co.kr/trainer/trainerScoreYearRecord.do"
        qs = {"Act":"10","Sub":"2","meet":meet}
        key = "조교사명"
    try:
        r = S.get(url, params=qs, timeout=25)
        r.raise_for_status()
        soup = BeautifulSoup(decode_response(r), "html.parser")
        table = None
        for t in soup.find_all("table"):
            txt = clean(t.get_text(" ", strip=True))
            if key in txt and "총" in txt and "승률" in txt:
                table = t
                break
        if table is None:
            return {}
        out = {}
        for row in table_rows(table):
            if len(row) < 8 or not row[0].isdigit():
                continue
            name = norm_person_name(row[1])
            wins, seconds, thirds, starts = map(inum, row[2:6])
            if not name or starts < 0:
                continue
            out[name] = {
                "starts": starts,
                "wins": wins,
                "seconds": seconds,
                "thirds": thirds,
                "win_rate": wins / starts if starts else 0.0,
                "quinella_rate": (wins + seconds) / starts if starts else 0.0,
                "place_rate": (wins + seconds + thirds) / starts if starts else 0.0,
            }
        return out
    except Exception:
        return {}

def fetch_track_snapshot(meet):
    sub = "10" if meet == 1 else "9"
    url = "https://race.kra.co.kr/chulmainfo/trackView.do"
    try:
        r = S.get(url, params={"Act":"02","Sub":sub,"meet":meet}, timeout=25)
        r.raise_for_status()
        soup = BeautifulSoup(decode_response(r), "html.parser")
        txt = clean(soup.get_text(" ", strip=True))
        dm = re.search(r"(20\d{2})년\s*(\d{1,2})월\s*(\d{1,2})일(?:\([^)]*\))?\s*(\d{1,2})시\s*(\d{1,2})분", txt)
        mm = re.search(r"함수율\s*:\s*(\d+)\s*%\s*\(([^)]+)\)", txt)
        sm = re.search(r"모래두께\s*:\s*평균\s*([\d.]+)\s*cm", txt)
        if not dm and not mm:
            return None
        date = None
        observed_at = None
        if dm:
            y, mo, da, hh, mi = map(int, dm.groups())
            date = f"{y:04d}{mo:02d}{da:02d}"
            observed_at = f"{y:04d}-{mo:02d}-{da:02d}T{hh:02d}:{mi:02d}:00+09:00"
        return {
            "date": date,
            "observed_at": observed_at,
            "moisture_pct": int(mm.group(1)) if mm else None,
            "condition": clean(mm.group(2)) if mm else None,
            "sand_cm": float(sm.group(1)) if sm else None,
        }
    except Exception:
        return None

def attach_live_context(races, jockey_stats, trainer_stats, tracks):
    for race in races:
        meet = next((m for m, v in MEETS.items() if v[0] == race.get("venue")), None)
        if meet is None:
            continue
        tr = tracks.get(meet)
        # Never attach a stale track snapshot to another date.
        race["track"] = tr if tr and tr.get("date") == race.get("date") else None
        for h in race.get("horses", []):
            jn = norm_person_name(h.get("jockey", ""))
            tn = norm_person_name(h.get("trainer", ""))
            h["jockey_stats_1y"] = jockey_stats.get(meet, {}).get(jn)
            h["trainer_stats_1y"] = trainer_stats.get(meet, {}).get(tn)
            h.setdefault("horse_weight", None)
            h.setdefault("horse_weight_change", None)

def enrich_weight(race, date, rc_no, meet, debug):
    """Attach race-day body weight only when KRA has actually published it."""
    try:
        html = get_html("chulmaDetailInfoWeight.do", params(date, rc_no, meet))
        soup = BeautifulSoup(html, "html.parser")
        table = None
        for t in soup.find_all("table"):
            txt = clean(t.get_text(" ", strip=True))
            if "마명" in txt and "금일체중" in txt and "증감" in txt:
                table = t
                break
        if table is None:
            return
        by_no = {h["number"]: h for h in race["horses"]}
        by_name = {h["name"]: h for h in race["horses"]}
        samples = []
        for row in table_rows(table):
            if len(row) < 4:
                continue
            h = None
            if row[0].isdigit():
                h = by_no.get(int(row[0]))
            if h is None:
                h = by_name.get(row[1] if len(row) > 1 else "")
            if h is None:
                continue
            wm = re.search(r"-?\d+(?:\.\d+)?", row[2] if len(row) > 2 else "")
            cm = re.search(r"-?\d+(?:\.\d+)?", row[3] if len(row) > 3 else "")
            # Blank current weight means KRA has not entered race-day weight yet.
            h["horse_weight"] = float(wm.group()) if wm else None
            h["horse_weight_change"] = float(cm.group()) if (wm and cm) else None
            if len(row) > 5:
                h["previous_weight"] = fnum(row[5], 0) or None
            if len(row) > 6:
                h["average_weight"] = fnum(row[6], 0) or None
            if len(samples) < 3:
                samples.append(row[:8])
        debug["weight_samples"] = samples
    except Exception as e:
        debug["weight_error"] = repr(e)

def main():
    kst = ZoneInfo("Asia/Seoul")
    now = datetime.now(kst)
    # Keep the previous two KST dates as well as today's and upcoming race cards.
    today = now.strftime("%Y%m%d")
    # Some hosted runners cannot reach KRA. Fail before repeatedly querying every
    # race and before replacing the last successful data with a partial document.
    probe = S.get(f"{BASE}/chulmaDetailInfoChulmapyo.do", params=params(today, 1, 1), timeout=(5, 10))
    probe.raise_for_status()
    print("KRA connectivity confirmed", flush=True)
    dates = [(now + timedelta(days=i)).strftime("%Y%m%d") for i in range(-2, 3)]
    previous_map = {}
    previous_complete = False
    try:
        previous_doc = json.loads(Path("data/latest.json").read_text(encoding="utf-8"))
        previous_complete = previous_doc.get("status", {}).get("error_count") == 0
        for r in previous_doc.get("races", []):
            previous_map[(str(r.get("date")), r.get("venue"), int(r.get("race_no") or 0))] = r
    except Exception:
        pass
    jockey_stats = {meet: fetch_person_stats("jockey", meet) for meet in MEETS}
    trainer_stats = {meet: fetch_person_stats("trainer", meet) for meet in MEETS}
    tracks = {meet: fetch_track_snapshot(meet) for meet in MEETS}
    races, errors, debug_race = [], [], None
    for date in dates:
        for meet in MEETS:
            archived = [r for (d, v, _), r in previous_map.items()
                        if d == date and v == MEETS[meet][0] and r.get("historical_view")]
            if date < today and previous_complete and archived:
                races.extend(sorted(archived, key=lambda r: r["race_no"]))
                continue
            misses = 0
            consecutive_errors = 0
            for rc_no in range(1, 17):
                try:
                    race, dbg = parse_card(date, rc_no, meet)
                    consecutive_errors = 0
                    if not race:
                        misses += 1
                        # After several consecutive missing races, higher race numbers won't exist.
                        if misses >= 3 and rc_no >= 4:
                            break
                        continue
                    misses = 0
                    prev = previous_map.get((date, MEETS[meet][0], rc_no))
                    reused = reuse_static_horse_data(race, prev)
                    if not reused:
                        enrich_record(race, date, rc_no, meet, dbg)
                        enrich_distance(race, date, rc_no, meet, dbg)
                        enrich_recent(race, date, rc_no, meet, dbg)
                    dbg["static_reused"] = reused
                    if date == today:
                        enrich_weight(race, date, rc_no, meet, dbg)
                    if date < today:
                        race["historical_view"] = True
                    races.append(race)
                    if debug_race is None:
                        debug_race = {"date":date,"meet":meet,"rc_no":rc_no,**dbg}
                    print(f"OK {date} meet={meet} race={rc_no} horses={len(race['horses'])}")
                    time.sleep(0.12)
                except Exception as e:
                    consecutive_errors += 1
                    errors.append({"date":date,"meet":meet,"race_no":rc_no,"error":repr(e)})
                    print(f"ERR {date} meet={meet} race={rc_no}: {e}", file=sys.stderr)
                    if consecutive_errors >= 2:
                        raise RuntimeError("Repeated card failures; preserving the last published data") from e
                    time.sleep(0.3)
    attach_live_context([r for r in races if not r.get("historical_view")], jockey_stats, trainer_stats, tracks)
    print("Refreshing historical context", flush=True)
    v7_status = {"status": "unavailable"}
    try:
        from refresh_v7 import refresh_and_attach as refresh_v7
        v7_status = refresh_v7(races)
    except Exception as e:
        v7_status = {"status": "error", "error": str(e)}
    from results_kra import attach_results
    print("Refreshing official dividends", flush=True)
    result_status = attach_results(races, previous_map, now, S, decode_response)
    out = {
        "updated_at": now.isoformat(timespec="seconds"),
        "races": races,
        "status": {
            "race_count": len(races),
            "error_count": len(errors),
            "dates": dates,
            "results": result_status,
            "history_v7": v7_status,
            "note": "Official race cards and settled results; no live odds collection.",
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
