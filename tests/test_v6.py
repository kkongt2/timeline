import copy
import gzip
import json
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/model-research'))
from features_v6 import History,prepare,validate_rows,attach

class TemporalTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.rows=[json.loads(x) for x in gzip.decompress((ROOT/'training/history.jsonl.gz').read_bytes()).splitlines()][:25]
 def test_no_future_or_same_day_labels(self):
  a,_=prepare(self.rows)
  changed=copy.deepcopy(self.rows)
  for r in changed:
   if r['date']>=self.rows[-1]['date']:
    n=len(r['horses'])
    for h in r['horses']:h['finish']=n+1-h['finish'];h['race_seconds']=999;h['horse_weight']=999
  b,_=prepare(changed)
  for x,y in zip(a,b):self.assertEqual(x['X'],y['X'])
 def test_field_order_invariance(self):
  a,_=prepare(self.rows);changed=[dict(r,horses=list(reversed(r['horses']))) for r in self.rows];b,_=prepare(changed)
  for x,y in zip(a,b):self.assertEqual(x['X'],y['X']);self.assertEqual(x['numbers'],y['numbers'])
 def test_training_live_roundtrip(self):
  cut=self.rows[-1]['date'];prior=[r for r in self.rows if r['date']<cut];future=[r for r in self.rows if r['date']==cut]
  _,history=prepare(prior);expected=[history.field(r)[1] for r in future];live=copy.deepcopy(future);attach(live,json.loads(json.dumps(history.export())))
  for r,X in zip(live,expected):self.assertEqual([h['features_v6'] for h in sorted(r['horses'],key=lambda h:h['number'])],X)
  stale=copy.deepcopy(future);bad=history.export();bad['through']=cut;attach(stale,bad);self.assertTrue(all('feature_version' not in r for r in stale))
 def test_duplicate_and_invalid_results_rejected(self):
  rows,issues=validate_rows([self.rows[0],self.rows[0]]);self.assertEqual(len(rows),1);self.assertEqual(issues[0]['reason'],'duplicate_race')
  bad=copy.deepcopy(self.rows[0]);bad['horses'][1]['finish']=bad['horses'][0]['finish'];self.assertEqual(len(validate_rows([bad])[0]),0)
 def test_current_weight_does_not_change_features(self):
  h=History();r=copy.deepcopy(self.rows[0]);a=h.field(r)[1]
  for horse in r['horses']:horse['horse_weight']=1000;horse['horse_weight_change']=100
  self.assertEqual(a,h.field(r)[1])

if __name__=='__main__':unittest.main()
