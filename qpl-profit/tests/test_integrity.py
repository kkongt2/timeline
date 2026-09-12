import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from collect_payouts import payouts
from features_v7 import History

class Integrity(unittest.TestCase):
    def test_sales_not_dividends(self):
        self.assertEqual(payouts('복연: 1,000,000\n배당률 단: ①2.0\n복연: ①②3.2 ①③8.0 ②③4.1\n',[1,2,3]),{'1-2':3.2,'1-3':8.,'2-3':4.1})
    def test_missing_and_malformed_never_zero(self):
        for s in ['복연: 1,000,000','배당률 단: ①2.0\n복연: ①②3.2','배당률 단: ①2.0\n복연: ①②3.2 ①③8.0 ②③4.1 오류','배당률 단: ①2.0\n복연: ①②3.2 ①③8.0 ②③4.1 ①②3.2']:
            with self.assertRaises(ValueError):payouts(s,[1,2,3])
    def test_current_result_and_dividend_not_features(self):
        r=dict(date='20260912',venue='seoul',race_no=1,distance=1200,grade='국6등급',place_k=2,place_winners=[1,2],horses=[dict(number=i,name=f'horse{i}',age=3,sex='수',rating=10*i,burden=54,jockey='j',trainer='t',finish=i) for i in range(1,5)])
        history=History();x=history.field(r)[1];after=copy.deepcopy(r)
        after['payouts']={'1-2':9999};after['place_winners']=[4,3]
        for h in after['horses']:h.update(finish=5-h['finish'],race_seconds=99,early_position=4)
        self.assertEqual(x,history.field(after)[1])
        history.add_day([r]);self.assertEqual(x,history.field(r)[1])

if __name__=='__main__':unittest.main()
