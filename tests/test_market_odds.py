import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from market_odds import parse_report

class MarketOdds(unittest.TestCase):
    def test_place_columns_and_other_market_exclusion(self):
        report='''제목 : 25년09월28일(일) 제 1경주
순위 마번 G-3Ｆ S-1F G-1F 단승식 연승식
1 10 36.3 0:13.7 12.4 4.2 1.4
4 11 37.9 0:13.4 13.6 10.5 2.8
취소 2 0.0 0.0 0.0 0.0 0.0
(복승식 배당률)
1- 2 123.7
배당률 단: ⑩4.2 연: ⑩1.4 복: ⑩⑫4.7
'''
        result=parse_report(report,'20250928')[1]
        self.assertEqual(result['place']['quotes'],[dict(numbers=[10],odds=1.4),dict(numbers=[11],odds=2.8)])
        self.assertEqual(result['pair']['quotes'],[])
        with self.assertRaises(ValueError):parse_report(report,'20250927')
        with self.assertRaises(ValueError):parse_report(report.replace('(복승식 배당률)','1 10 36.3 0:13.7 12.4 4.2 1.4\n(복승식 배당률)'),'20250928')

if __name__=='__main__':unittest.main()
