import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from results_kra import parse_result


class OfficialResults(unittest.TestCase):
    race = {'date': '20260910', 'race_no': 1, 'venue': 'jeju'}

    def page(self, place='⑥ 1.1 ③ 1.9', pair='⑥③ 1.5 ⑥① 1.7 ③① 2.5', trio='⑥③① 7.8'):
        return ('<table><tr><td>2026년 09월 10일 (목) 제1경주 제주</td></tr></table>'
                '<table><caption>매출액</caption><tr><td>연승식: 999999</td></tr></table>'
                '<table><caption>배당률의 정보를 제공하는 표</caption><tr>'
                f'<td>연승식: {place}</td><td>복연승식: {pair}</td><td>삼복승식: {trio}</td></tr></table>')

    def test_official_markets_and_two_place_winners(self):
        result = parse_result(self.page(), self.race)
        self.assertEqual(result['status'], 'confirmed')
        self.assertEqual(result['place']['payouts'], [{'numbers': [6], 'odds': 1.1}, {'numbers': [3], 'odds': 1.9}])
        self.assertEqual(result['pair']['payouts'][0], {'numbers': [3, 6], 'odds': 1.5})
        self.assertEqual(result['trio']['payouts'], [{'numbers': [1, 3, 6], 'odds': 7.8}])

    def test_wrong_date_round_and_venue_rejected(self):
        for key, value in [('date', '20260911'), ('race_no', 2), ('venue', 'seoul')]:
            with self.assertRaises(ValueError):
                parse_result(self.page(), {**self.race, key: value})

    def test_dead_heat_extra_payouts_preserved(self):
        result = parse_result(self.page(pair='①② 1.1 ①③ 1.2 ①④ 1.3 ②③ 2.0 ②④ 2.1'), self.race)
        self.assertEqual(len(result['pair']['payouts']), 5)

    def test_no_invented_results_when_incomplete(self):
        self.assertEqual(parse_result('', self.race)['status'], 'pending')
        for value in ['', '①② ?', '①② 2.0 ③④ 미확정']:
            result = parse_result(self.page(pair=value), self.race)
            self.assertEqual(result['pair']['status'], 'pending')
            self.assertEqual(result['pair']['payouts'], [])
        self.assertEqual(parse_result(self.page(pair='전액환불'), self.race)['pair']['status'], 'refunded')

    def test_duplicate_or_invalid_dividend_rejected(self):
        for value in ['①① 2.0', '①② 2.0 ②① 3.0', '①② 0.9']:
            with self.assertRaises(ValueError):
                parse_result(self.page(pair=value), self.race)
        for value in ['①①③ 2.0', '①②③ 2.0 ③②① 3.0', '①②③ 0.9']:
            with self.assertRaises(ValueError):
                parse_result(self.page(trio=value), self.race)


if __name__ == '__main__':
    unittest.main()
