import csv
import os
import unittest

from bot.sizing import RiskGuard, SymbolSpec, compute_lots, drawdown_throttle

XAU = SymbolSpec(tick_size=0.01, tick_value_loss=1.0, volume_min=0.01, volume_step=0.01, volume_max=100, commission_per_lot_rt=10)
EUR = SymbolSpec(tick_size=0.00001, tick_value_loss=1.0, volume_min=0.01, volume_step=0.01, volume_max=100, commission_per_lot_rt=10)
VECTORS = os.path.join(os.path.dirname(__file__), "vectors", "sizing_vectors.csv")


class ComputeLots(unittest.TestCase):
    def test_gold_1000_usd(self):
        # budget 7.50; loss/lot = 600 ticks * $1 + $10 = 610; raw 0.0123 -> 0.01
        r = compute_lots(balance=1000, equity=1000, risk_pct=0.75, sl_distance=6.0, spec=XAU)
        self.assertTrue(r.ok)
        self.assertEqual(r.lots, 0.01)
        self.assertAlmostEqual(r.risk_budget, 7.5)
        self.assertAlmostEqual(r.actual_risk, 6.10)

    def test_refuses_instead_of_min_lot(self):
        r = compute_lots(balance=300, equity=300, risk_pct=0.75, sl_distance=6.0, spec=XAU)
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, "below_min_volume")
        self.assertEqual(r.lots, 0.0)

    def test_eurusd_300_usd(self):
        # 15 pips = 0.0015 = 150 ticks; loss/lot = 150 + 10 = 160; budget 2.25 -> 0.0140 -> 0.01
        r = compute_lots(balance=300, equity=300, risk_pct=0.75, sl_distance=0.0015, spec=EUR)
        self.assertTrue(r.ok)
        self.assertEqual(r.lots, 0.01)
        self.assertAlmostEqual(r.actual_risk, 1.60)

    def test_uses_lower_of_balance_and_equity(self):
        r = compute_lots(balance=5000, equity=4000, risk_pct=1.0, sl_distance=6.0, spec=XAU)
        self.assertEqual(r.base, 4000)
        self.assertEqual(r.lots, 0.06)  # 40 / 610 = 0.0655 -> 0.06

    def test_always_rounds_down(self):
        # budget 12.19 / 610 = 0.019983 -> must be 0.01, never 0.02
        r = compute_lots(balance=1219, equity=1219, risk_pct=1.0, sl_distance=6.0, spec=XAU)
        self.assertEqual(r.lots, 0.01)
        self.assertLessEqual(r.actual_risk, r.risk_budget)

    def test_exact_step_boundary_not_lost_to_float_error(self):
        # budget exactly 12.20 -> 0.02 lots exactly
        r = compute_lots(balance=1220, equity=1220, risk_pct=1.0, sl_distance=6.0, spec=XAU)
        self.assertEqual(r.lots, 0.02)

    def test_ai_multiplier_only_reduces(self):
        full = compute_lots(balance=10000, equity=10000, risk_pct=0.75, sl_distance=6.0, spec=XAU)
        half = compute_lots(balance=10000, equity=10000, risk_pct=0.75, sl_distance=6.0, spec=XAU, ai_multiplier=0.5)
        over = compute_lots(balance=10000, equity=10000, risk_pct=0.75, sl_distance=6.0, spec=XAU, ai_multiplier=3.0)
        self.assertEqual(full.lots, 0.12)
        self.assertEqual(half.lots, 0.06)
        self.assertEqual(over.lots, full.lots)
        blocked = compute_lots(balance=10000, equity=10000, risk_pct=0.75, sl_distance=6.0, spec=XAU, ai_multiplier=0)
        self.assertEqual(blocked.reason, "ai_blocked")

    def test_margin_cap(self):
        r = compute_lots(balance=10000, equity=10000, risk_pct=0.75, sl_distance=6.0, spec=XAU,
                         free_margin=1000, margin_per_lot=5000)  # 300 / 5000 = 0.06
        self.assertEqual(r.lots, 0.06)
        r2 = compute_lots(balance=10000, equity=10000, risk_pct=0.75, sl_distance=6.0, spec=XAU,
                          free_margin=100, margin_per_lot=5000)
        self.assertEqual(r2.reason, "insufficient_margin")

    def test_volume_max_and_invalid_inputs(self):
        small_max = SymbolSpec(0.01, 1.0, 0.01, 0.01, 0.05, 0)
        r = compute_lots(balance=1e6, equity=1e6, risk_pct=1, sl_distance=6.0, spec=small_max)
        self.assertEqual(r.lots, 0.05)
        self.assertEqual(compute_lots(balance=0, equity=0, risk_pct=1, sl_distance=6, spec=XAU).reason, "no_funds")
        self.assertEqual(compute_lots(balance=1000, equity=1000, risk_pct=1, sl_distance=0, spec=XAU).reason, "invalid_stop")
        self.assertEqual(compute_lots(balance=1000, equity=1000, risk_pct=50, sl_distance=6, spec=XAU).reason, "invalid_risk_pct")


class Throttle(unittest.TestCase):
    def test_levels(self):
        self.assertEqual(drawdown_throttle(95, 100), 1.0)
        self.assertEqual(drawdown_throttle(90, 100), 0.5)
        self.assertEqual(drawdown_throttle(85, 100), 0.25)
        self.assertEqual(drawdown_throttle(80, 100), 0.0)


class Guard(unittest.TestCase):
    def test_daily_weekly_total(self):
        g = RiskGuard(day_start_equity=1000, week_start_equity=1000, peak_equity=1000)
        self.assertEqual(g.update(985), "ok")
        self.assertEqual(g.update(980), "daily_lock")
        g.on_new_day(980)
        self.assertEqual(g.update(960), "daily_lock")
        g.on_new_day(960)
        self.assertEqual(g.update(950), "weekly_lock")
        g.on_new_week(950)
        g.on_new_day(950)
        self.assertEqual(g.update(1100), "ok")   # new peak
        g.on_new_day(900); g.on_new_week(900)
        self.assertEqual(g.update(880), "total_halt")  # 20% below 1100

    def test_withdrawal_is_not_a_loss(self):
        g = RiskGuard(day_start_equity=1000, week_start_equity=1000, peak_equity=1000)
        g.on_cash_flow(-500)
        self.assertEqual(g.update(500), "ok")


class MqlParityVectors(unittest.TestCase):
    """The same CSV is replayed by mt5/Scripts/SizingSelfTest.mq5 inside MetaTrader."""

    def test_vectors_match_reference(self):
        with open(VECTORS, newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertGreater(len(rows), 10)
        for row in rows:
            spec = SymbolSpec(float(row["tick_size"]), float(row["tick_value_loss"]), float(row["volume_min"]),
                              float(row["volume_step"]), float(row["volume_max"]), float(row["commission_rt"]))
            r = compute_lots(balance=float(row["balance"]), equity=float(row["equity"]), risk_pct=float(row["risk_pct"]),
                             sl_distance=float(row["sl_distance"]), spec=spec, ai_multiplier=float(row["ai_mult"]),
                             dd_multiplier=float(row["dd_mult"]))
            with self.subTest(case=row["case"]):
                self.assertEqual(r.reason, row["expected_reason"])
                self.assertAlmostEqual(r.lots, float(row["expected_lots"]), places=8)


if __name__ == "__main__":
    unittest.main()
