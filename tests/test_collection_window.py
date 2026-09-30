import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from update_kra import collection_dates


class CollectionWindow(unittest.TestCase):
    def test_wednesday_includes_published_october_weekend(self):
        dates = collection_dates(datetime(2026, 9, 30, 21, tzinfo=ZoneInfo('Asia/Seoul')))
        self.assertEqual(dates[0], '20260928')
        self.assertEqual(dates[-1], '20261007')
        self.assertIn('20261003', dates)
        self.assertIn('20261004', dates)
        self.assertEqual(len(set(dates)), 10)

    def test_uses_kst_day_at_utc_midnight_boundary(self):
        dates = collection_dates(datetime(2026, 9, 30, 16, tzinfo=timezone.utc))
        self.assertEqual((dates[0], dates[-1]), ('20260929', '20261008'))

    def test_year_and_leap_day_boundaries(self):
        kst = ZoneInfo('Asia/Seoul')
        self.assertEqual(collection_dates(datetime(2026, 12, 30, tzinfo=kst))[-1], '20270106')
        dates = collection_dates(datetime(2028, 2, 28, tzinfo=kst))
        self.assertIn('20280229', dates)
        self.assertEqual(dates[-1], '20280306')


if __name__ == '__main__':
    unittest.main()
