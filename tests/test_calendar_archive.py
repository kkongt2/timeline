import sys,unittest
from pathlib import Path
from datetime import datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from calendar_archive import dividends,window_start

class CalendarArchive(unittest.TestCase):
    def test_complete_previous_weeks(self):
        self.assertEqual(window_start(datetime(2026,9,12)),'20260824')
        self.assertEqual(window_start(datetime(2026,9,14)),'20260831')
    def test_both_markets_and_sales_heading(self):
        s='복연: 10,000,000\n배당률 단: ①2.0 연: ①1.2 ②1.5 복: ①②4.0\n복연: ①②2.0 ①③3.1 ②③4.2\n'
        self.assertEqual(dividends(s,'place',[(1,),(2,)])['payouts'][1]['odds'],1.5)
        self.assertEqual(len(dividends(s,'pair',[(1,2),(1,3),(2,3)])['payouts']),3)
        with self.assertRaises(ValueError):dividends(s,'place',[(1,),(3,)])
        with self.assertRaises(ValueError):dividends(s.replace('②③4.2','②③4.2 오류'),'pair',[(1,2),(1,3),(2,3)])

if __name__=='__main__':unittest.main()
