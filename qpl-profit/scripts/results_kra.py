"""Display official settled dividends separately from model inputs."""
import math
import re
from datetime import datetime, timedelta
from urllib.parse import urlencode

from bs4 import BeautifulSoup

VENUES = {'seoul': (1, '서울'), 'jeju': (2, '제주'), 'busan': (3, '부경')}
CIRCLES = {chr(0x2460 + i): i + 1 for i in range(20)}


def result_url(race):
    return 'https://race.kra.co.kr/raceScore/ScoretableDetailList.do?' + urlencode({
        'Act': '04', 'Sub': '1', 'meet': VENUES[race['venue']][0],
        'realRcDate': race['date'], 'realRcNo': race['race_no'],
    })


def parse_result(html, race):
    soup = BeautifulSoup(html, 'html.parser')
    # Validate the visible race header, not request parameters echoed in a form.
    header = next((td.get_text(' ', strip=True) for td in soup.select('td')
                   if re.search(r'20\d{2}년\s*\d+월\s*\d+일.*제\s*\d+경주', td.get_text(' ', strip=True))), '')
    m = re.search(r'(20\d{2})년\s*(\d+)월\s*(\d+)일.*?제\s*(\d+)경주\s*(\S+)', header)
    if not m:
        return {'status': 'pending'}
    y, mo, day, rn, venue = m.groups()
    if (f'{int(y):04d}{int(mo):02d}{int(day):02d}' != str(race['date'])
            or int(rn) != int(race['race_no']) or venue not in ({'부경', '부산경남', '영남'} if race['venue'] == 'busan' else {VENUES[race['venue']][1]})):
        raise ValueError('Official result race identity mismatch')
    table = next((t for t in soup.select('table')
                  if t.find('caption') and '배당률' in t.find('caption').get_text()), None)
    if table is None:
        return {'status': 'pending'}
    markets = {}
    for kind, label, size in [('place', '연승식', 1), ('pair', '복연승식', 2)]:
        cell = next((td.get_text(' ', strip=True) for td in table.select('td')
                     if re.match(r'^' + label + r'\s*:', td.get_text(' ', strip=True))), '')
        value = cell.split(':', 1)[-1].strip()
        pattern = r'([①-⑳](?:\s*[①-⑳]){' + str(size - 1) + r'})\s+(\d+(?:\.\d+)?)'
        matches = list(re.finditer(pattern, value))
        if not matches or re.sub(pattern, '', value).strip():
            markets[kind] = {'status': 'refunded' if '환불' in value else 'pending', 'payouts': []}
            continue
        payouts = []
        seen = set()
        for match in matches:
            numbers = sorted(CIRCLES[c] for c in match[1] if c in CIRCLES)
            odds = float(match[2])
            key = tuple(numbers)
            if len(set(numbers)) != size or key in seen or not math.isfinite(odds) or odds < 1:
                raise ValueError('Invalid official dividend')
            seen.add(key)
            payouts.append({'numbers': numbers, 'odds': odds})
        markets[kind] = {'status': 'confirmed', 'payouts': payouts}
    starters = []
    card = next((t for t in soup.select('table') if t.find('caption') and '경주상세성적' in t.find('caption').get_text()), None)
    if card:
        for tr in card.select('tr'):
            cells = tr.find_all('td')
            if len(cells) < 3: continue
            position = cells[0].get_text(' ', strip=True); number = cells[1].get_text(' ', strip=True)
            if number.isdigit() and (position.isdigit() or position in ('중지','실격','주행중지')):
                starters.append(int(number))
    return {'status': 'confirmed' if all(v['status'] == 'confirmed' for v in markets.values()) else 'partial', 'starters': sorted(set(starters)) or None, **markets}


def attach_results(races, previous, now, session, decode):
    stats = {'confirmed': 0, 'pending': 0, 'errors': 0}
    for race in races:
        old = previous.get((str(race['date']), race['venue'], int(race['race_no'])), {}).get('official_result')
        race.pop('official_result', None)
        date = str(race['date'])
        try:
            start = datetime.strptime(date + ' ' + (race.get('start_time') or '23:59'), '%Y%m%d %H:%M').replace(tzinfo=now.tzinfo)
            if start > now:
                continue
            if old and old.get('version') == 2 and old.get('status') == 'confirmed':
                checked = datetime.fromisoformat(old['checked_at'])
                if timedelta(0) <= now - checked < timedelta(hours=6):
                    race['official_result'] = old
                    stats['confirmed'] += 1
                    continue
            url = result_url(race)
            response = session.get(url, timeout=(10, 25))
            response.raise_for_status()
            result = parse_result(decode(response), race)
            result.update(version=2, source=url, checked_at=now.isoformat(timespec='seconds'))
            race['official_result'] = result
            stats['confirmed' if result['status'] == 'confirmed' else 'pending'] += 1
        except Exception as exc:
            race['official_result'] = old if old and old.get('version') in (1, 2) and old.get('status') == 'confirmed' else {'status': 'unavailable', 'source': result_url(race)}
            stats['errors'] += 1
            print(f"Result unavailable {date} {race['venue']} {race['race_no']}: {exc}")
    return stats
