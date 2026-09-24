"""Regenerates sizing_vectors.csv from the Python reference (bot/sizing.py).

The CSV is the contract between the Python reference and the MQL5 port:
mt5/Scripts/SizingSelfTest.mq5 must reproduce every row.
"""
import csv
import os

from bot.sizing import SymbolSpec, compute_lots

GOLD = dict(tick_size=0.01, tick_value_loss=1.0, volume_min=0.01, volume_step=0.01, volume_max=100, commission_rt=10)
EUR = dict(tick_size=0.00001, tick_value_loss=1.0, volume_min=0.01, volume_step=0.01, volume_max=100, commission_rt=10)
CENT_EUR = dict(tick_size=0.00001, tick_value_loss=0.01, volume_min=0.01, volume_step=0.01, volume_max=1000, commission_rt=0)
IDX = dict(tick_size=0.1, tick_value_loss=0.1, volume_min=0.1, volume_step=0.1, volume_max=50, commission_rt=0.7)

CASES = [
    ("gold_1000", GOLD, 1000, 1000, 0.75, 6.0, 1, 1),
    ("gold_300_refused", GOLD, 300, 300, 0.75, 6.0, 1, 1),
    ("gold_3000", GOLD, 3000, 3000, 0.75, 6.0, 1, 1),
    ("gold_equity_below_balance", GOLD, 5000, 4000, 1.0, 6.0, 1, 1),
    ("gold_round_down", GOLD, 1219, 1219, 1.0, 6.0, 1, 1),
    ("gold_exact_boundary", GOLD, 1220, 1220, 1.0, 6.0, 1, 1),
    ("gold_ai_half", GOLD, 10000, 10000, 0.75, 6.0, 0.5, 1),
    ("gold_ai_block", GOLD, 10000, 10000, 0.75, 6.0, 0, 1),
    ("gold_dd_quarter", GOLD, 10000, 8500, 0.75, 6.0, 1, 0.25),
    ("gold_dd_halt", GOLD, 10000, 8000, 0.75, 6.0, 1, 0),
    ("eur_300", EUR, 300, 300, 0.75, 0.0015, 1, 1),
    ("eur_150_refused", EUR, 150, 150, 0.75, 0.0015, 1, 1),
    ("eur_25000", EUR, 25000, 25000, 0.5, 0.0020, 1, 1),
    ("cent_eur_small", CENT_EUR, 30, 30, 0.75, 0.0015, 1, 1),
    ("index_step_0_1", IDX, 20000, 20000, 0.5, 25.0, 1, 1),
    ("invalid_stop", GOLD, 1000, 1000, 0.75, 0.0, 1, 1),
    ("no_funds", GOLD, 0, 0, 0.75, 6.0, 1, 1),
]


def main():
    path = os.path.join(os.path.dirname(__file__), "sizing_vectors.csv")
    fields = ["case", "balance", "equity", "risk_pct", "sl_distance", "ai_mult", "dd_mult", "tick_size",
              "tick_value_loss", "volume_min", "volume_step", "volume_max", "commission_rt",
              "expected_lots", "expected_reason"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for name, s, bal, eq, risk, sl, ai, dd in CASES:
            spec = SymbolSpec(s["tick_size"], s["tick_value_loss"], s["volume_min"], s["volume_step"], s["volume_max"], s["commission_rt"])
            r = compute_lots(balance=bal, equity=eq, risk_pct=risk, sl_distance=sl, spec=spec, ai_multiplier=ai, dd_multiplier=dd)
            w.writerow({"case": name, "balance": bal, "equity": eq, "risk_pct": risk, "sl_distance": sl, "ai_mult": ai,
                        "dd_mult": dd, **s, "expected_lots": f"{r.lots:.2f}", "expected_reason": r.reason})
    print(path)


if __name__ == "__main__":
    main()
