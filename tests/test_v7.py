import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/model-research'))
from features_v7 import History,prepare,attach
from train_v7 import pair_features

def race(date='20260101'):
    return dict(date=date,venue='seoul',race_no=1,distance=1200,grade='국5등급',place_k=2,place_winners=[1,2],horses=[
        dict(number=i,name='말'+str(i),finish=i,age=4,sex='수',rating=30+i,burden=55,jockey='기수'+str(i),trainer='조교사',
             race_seconds=73+i,early_position=i,early_seconds=13+i*.1,last_seconds=12+i*.2) for i in range(1,7)])

class Features(unittest.TestCase):
    def test_pre_race_and_same_day_isolation(self):
        past=race();target=race('20260103');a,_=prepare([past,target]);changed=copy.deepcopy(target)
        for h in changed['horses']:h.update(finish=7-h['finish'],early_seconds=99,last_seconds=99,race_seconds=999)
        b,_=prepare([past,changed]);self.assertEqual(a[-1]['X'],b[-1]['X'])
        same=race();same['race_no']=2;c,_=prepare([past,same]);self.assertEqual(c[0]['X'],c[1]['X'])

    def test_real_place_is_not_top_three(self):
        store=History();store.add_day([race()]);_,X,_=store.field(race('20260103'))
        self.assertGreater(X[2][0],X[2][32]);self.assertGreater(X[0][32],X[2][32])

    def test_serving_parity_and_permutation(self):
        past=race();future=race('20260103');prepared,store=prepare([past]);context=store.export()
        expected=store.field(future)[1];attach([future],context)
        self.assertEqual(expected,[h['features_v7'] for h in future['horses']])
        future['horses'].reverse();_,X,_=store.field(future);self.assertEqual(expected,X)
        import numpy as np
        pair,ij=pair_features(np.asarray(X));self.assertEqual(pair.shape[1],149)
        changed=np.asarray(X).copy();changed[5,30]=.9;other,_=pair_features(changed)
        self.assertNotEqual(pair[0].tolist(),other[0].tolist())

    def test_distinct_cohort_and_missing_pace(self):
        store=History();store.add_day([race()]);future=race('20260103');future['horses'][0]['age']=3
        _,X,q=store.field(future);self.assertEqual(X[0][51],0);self.assertEqual(q[0]['pace_starts'],0)

if __name__=='__main__':unittest.main()
