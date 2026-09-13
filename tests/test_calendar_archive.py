import sys,unittest,json,os,tempfile
from pathlib import Path
from datetime import datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from calendar_archive import dividends,window_start,extend,publish

class CalendarArchive(unittest.TestCase):
    def test_rolling_year_and_leap_day(self):
        self.assertEqual(window_start(datetime(2026,9,13)),'20250913')
        self.assertEqual(window_start(datetime(2026,9,14)),'20250914')
        self.assertEqual(window_start(datetime(2024,2,29)),'20230228')
        self.assertEqual(window_start(datetime(2025,3,1)),'20240301')
    def test_daily_archive_preservation_priority_and_expiry(self):
        old=os.getcwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory);Path('data').mkdir()
                card=lambda date,venue='seoul',**kw:dict(date=date,venue=venue,race_no=1,**kw)
                now=datetime(2026,9,13)
                rows=[card('20250912'),card('20250913'),card('20260901'),card('20260901','jeju'),card('20260913')]
                index=publish(rows,now)
                self.assertEqual([x['date'] for x in index],['20250913','20260901','20260913'])
                self.assertEqual(index[1]['venues'],['jeju','seoul'])
                Path('data/calendar-archive.json').write_text(json.dumps(dict(races=[card('20250913',seed=True)])))
                loaded=extend([card('20260901',fresh=True),card('20250912')],now)
                self.assertEqual(len(loaded),3)
                self.assertTrue(next(r for r in loaded if r['date']=='20260901' and r['venue']=='seoul')['fresh'])
                self.assertNotIn('seed',loaded[0])
                publish(loaded,datetime(2026,9,14))
                self.assertFalse(Path('data/calendar/20250913.json').exists())
                self.assertTrue(Path('data/calendar/20260901.json').exists())
            finally:os.chdir(old)
    def test_both_markets_and_sales_heading(self):
        s='복연: 10,000,000\n배당률 단: ①2.0 연: ①1.2 ②1.5 복: ①②4.0\n복연: ①②2.0 ①③3.1 ②③4.2\n'
        self.assertEqual(dividends(s,'place',[(1,),(2,)])['payouts'][1]['odds'],1.5)
        self.assertEqual(len(dividends(s,'pair',[(1,2),(1,3),(2,3)])['payouts']),3)
        with self.assertRaises(ValueError):dividends(s,'place',[(1,),(3,)])
        with self.assertRaises(ValueError):dividends(s.replace('②③4.2','②③4.2 오류'),'pair',[(1,2),(1,3),(2,3)])

if __name__=='__main__':unittest.main()
