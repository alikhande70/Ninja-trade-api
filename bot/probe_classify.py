"""Classifies what market data an MT5 account really provides.

Input: the JSON written by mt5/Scripts/DataProbe.mq5 on the account under
test. Output: one verdict per symbol, separating what MetaTrader supports
in general from what this account, server and symbol actually deliver.

Usage: python -m bot.probe_classify path/to/probe.json
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass

EXCHANGE_L2 = "EXCHANGE_L2"          # real depth from an exchange with volumes
BROKER_DEPTH = "BROKER_DEPTH"        # multi-level quotes with volumes from an OTC broker
SYNTHETIC_LADDER = "SYNTHETIC_LADDER"  # levels without volumes, derived from bid/ask
TOP_OF_BOOK_ONLY = "TOP_OF_BOOK_ONLY"  # no depth at all: bid/ask ticks only

DESCRIPTIONS = {
    EXCHANGE_L2: "Real exchange order book with volumes; the original L2 goal is possible.",
    BROKER_DEPTH: "Depth comes from the broker's own quotes (OTC), not a market-wide order book.",
    SYNTHETIC_LADDER: "Depth window is a price ladder built from bid/ask; no volumes, no L2 information.",
    TOP_OF_BOOK_ONLY: "Only bid/ask ticks are available; no order book.",
}


@dataclass(frozen=True)
class Verdict:
    symbol: str
    level: str
    reasons: tuple[str, ...]
    has_real_trade_volume: bool
    tick_count: int


def classify_symbol(s: dict) -> Verdict:
    reasons: list[str] = []
    book = s.get("book", {})
    ticks = s.get("ticks", {})
    exemode = s.get("trade_exemode", "")
    calc_mode = s.get("calc_mode", "")
    is_exchange = exemode == "SYMBOL_TRADE_EXECUTION_EXCHANGE" or calc_mode.startswith("SYMBOL_CALC_MODE_EXCH")
    reasons.append(f"execution={exemode or 'unknown'}, calc={calc_mode or 'unknown'}")

    subscribed = bool(book.get("subscribed"))
    max_bid = int(book.get("max_bid_levels", 0))
    max_ask = int(book.get("max_ask_levels", 0))
    with_volume = int(book.get("levels_with_volume", 0))
    distinct_volumes = int(book.get("distinct_volumes", 0))
    reasons.append(
        f"book subscribed={subscribed}, snapshots={book.get('snapshots', 0)}, "
        f"levels bid/ask={max_bid}/{max_ask}, levels with volume={with_volume}, "
        f"distinct volumes={distinct_volumes}"
    )

    real_volume_ticks = int(ticks.get("with_real_volume", 0)) + int(ticks.get("with_flag_volume", 0))
    has_trade_volume = real_volume_ticks > 0
    reasons.append(f"ticks={ticks.get('count', 0)}, ticks with trade volume={real_volume_ticks}")

    if not subscribed or max(max_bid, max_ask) == 0:
        level = TOP_OF_BOOK_ONLY
    elif with_volume == 0:
        level = SYNTHETIC_LADDER
    elif is_exchange and max_bid >= 2 and max_ask >= 2 and distinct_volumes >= 3:
        level = EXCHANGE_L2
    else:
        level = BROKER_DEPTH
        if distinct_volumes < 3:
            reasons.append("volumes barely change: likely fixed liquidity tiers")
    return Verdict(s.get("name", "?"), level, tuple(reasons), has_trade_volume, int(ticks.get("count", 0)))


def classify(probe: dict) -> list[Verdict]:
    return [classify_symbol(s) for s in probe.get("symbols", [])]


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    with open(argv[1], encoding="utf-8-sig") as f:
        probe = json.load(f)
    acc = probe.get("account", {})
    print(f"server={acc.get('server')} company={acc.get('company')} mode={acc.get('trade_mode')}")
    for v in classify(probe):
        print(f"\n{v.symbol}: {v.level}\n  {DESCRIPTIONS[v.level]}")
        for r in v.reasons:
            print(f"  - {r}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
