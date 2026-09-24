import json
import os
import unittest

from bot.probe_classify import BROKER_DEPTH, EXCHANGE_L2, SYNTHETIC_LADDER, TOP_OF_BOOK_ONLY, classify

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "probe_synthetic_otc.json")


class Classify(unittest.TestCase):
    def test_levels(self):
        with open(FIXTURE, encoding="utf-8") as f:
            verdicts = {v.symbol: v for v in classify(json.load(f))}
        self.assertEqual(verdicts["XAUUSD"].level, TOP_OF_BOOK_ONLY)
        self.assertEqual(verdicts["EURUSD"].level, SYNTHETIC_LADDER)
        self.assertEqual(verdicts["GBPUSD"].level, BROKER_DEPTH)
        self.assertEqual(verdicts["ESZ6"].level, EXCHANGE_L2)
        self.assertFalse(verdicts["EURUSD"].has_real_trade_volume)
        self.assertTrue(verdicts["ESZ6"].has_real_trade_volume)

    def test_otc_depth_with_volumes_is_never_exchange_l2(self):
        s = {"name": "X", "trade_exemode": "SYMBOL_TRADE_EXECUTION_MARKET", "calc_mode": "SYMBOL_CALC_MODE_FOREX",
             "book": {"subscribed": True, "max_bid_levels": 10, "max_ask_levels": 10, "levels_with_volume": 20, "distinct_volumes": 90},
             "ticks": {}}
        self.assertEqual(classify({"symbols": [s]})[0].level, BROKER_DEPTH)


if __name__ == "__main__":
    unittest.main()
