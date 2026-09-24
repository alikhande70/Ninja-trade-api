import unittest

from bot.orderbook import L2Book, SequenceGapError, top_level_ofi


class Book(unittest.TestCase):
    def setUp(self):
        self.b = L2Book()
        self.b.apply_snapshot(bids=[(100.0, 2.0), (99.5, 5.0)], asks=[(100.5, 1.0), (101.0, 4.0)], seq=10)

    def test_top_mid_spread_microprice(self):
        self.assertEqual(self.b.mid(), 100.25)
        self.assertEqual(self.b.spread(), 0.5)
        # (100*1 + 100.5*2) / 3 = 100.3333: leans toward the thinner ask side
        self.assertAlmostEqual(self.b.microprice(), 100.333333333, places=6)
        self.assertAlmostEqual(self.b.imbalance(2), (7 - 5) / 12)

    def test_delta_update_remove_and_stale(self):
        self.assertTrue(self.b.apply_delta(bids=[(100.0, 0.0)], asks=[(100.5, 3.0)], first_seq=11, last_seq=11))
        (bid,), (ask,) = self.b.top(1)
        self.assertEqual(bid, (99.5, 5.0))
        self.assertEqual(ask, (100.5, 3.0))
        self.assertFalse(self.b.apply_delta(bids=[(1.0, 1.0)], asks=[], first_seq=9, last_seq=11))
        self.assertNotIn(1.0, self.b.bids)

    def test_gap_raises(self):
        with self.assertRaises(SequenceGapError):
            self.b.apply_delta(bids=[], asks=[], first_seq=13, last_seq=14)

    def test_crossed(self):
        self.assertFalse(self.b.is_crossed())
        self.b.apply_delta(bids=[(101.0, 1.0)], asks=[], first_seq=11, last_seq=11)
        self.assertTrue(self.b.is_crossed())


class Ofi(unittest.TestCase):
    def test_signs(self):
        same = ((100, 5), (101, 5))
        self.assertEqual(top_level_ofi(*same, (100, 8), (101, 5)), 3)    # bid size up: buying
        self.assertEqual(top_level_ofi(*same, (100, 5), (101, 9)), -4)   # ask size up: selling
        self.assertEqual(top_level_ofi(*same, (100.5, 2), (101, 5)), 2)  # bid price up: new bid queue
        self.assertEqual(top_level_ofi(*same, (100, 5), (100.5, 3)), -3) # ask price down


if __name__ == "__main__":
    unittest.main()
