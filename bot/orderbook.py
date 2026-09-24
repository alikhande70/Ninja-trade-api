"""Venue-independent L2 order book with the features used by the research.

Kept separate from any exchange client so the same code runs on recorded
data and on a live feed. Only used if a venue with a real order book is
chosen (see docs/04-l2-impact-and-evidence.md).
"""
from __future__ import annotations

from dataclasses import dataclass, field


class SequenceGapError(Exception):
    """An update was missed; the book must be rebuilt from a new snapshot."""


@dataclass
class L2Book:
    bids: dict[float, float] = field(default_factory=dict)
    asks: dict[float, float] = field(default_factory=dict)
    last_seq: int | None = None

    def apply_snapshot(self, bids, asks, seq: int) -> None:
        self.bids = {p: q for p, q in bids if q > 0}
        self.asks = {p: q for p, q in asks if q > 0}
        self.last_seq = seq

    def apply_delta(self, bids, asks, first_seq: int, last_seq: int) -> bool:
        """Applies a diff. Returns False for a stale diff, raises on a gap."""
        if self.last_seq is None:
            raise SequenceGapError("no snapshot")
        if last_seq <= self.last_seq:
            return False
        if first_seq > self.last_seq + 1:
            raise SequenceGapError(f"expected {self.last_seq + 1}, got {first_seq}")
        for side, levels in ((self.bids, bids), (self.asks, asks)):
            for price, qty in levels:
                if qty > 0:
                    side[price] = qty
                else:
                    side.pop(price, None)
        self.last_seq = last_seq
        return True

    def top(self, n: int = 1):
        b = sorted(self.bids.items(), key=lambda x: -x[0])[:n]
        a = sorted(self.asks.items(), key=lambda x: x[0])[:n]
        return b, a

    def is_crossed(self) -> bool:
        (b,), (a,) = self.top(1)
        return b[0] >= a[0]

    def mid(self) -> float:
        (b,), (a,) = self.top(1)
        return (b[0] + a[0]) / 2

    def spread(self) -> float:
        (b,), (a,) = self.top(1)
        return a[0] - b[0]

    def microprice(self) -> float:
        """Mid weighted by the opposite side's size (leans toward the thin side)."""
        (b,), (a,) = self.top(1)
        (bp, bq), (ap, aq) = b, a
        return (bp * aq + ap * bq) / (bq + aq)

    def imbalance(self, levels: int = 5) -> float:
        """(bid qty - ask qty) / total over the top `levels`, in [-1, 1]."""
        b, a = self.top(levels)
        bq = sum(q for _, q in b)
        aq = sum(q for _, q in a)
        return 0.0 if bq + aq == 0 else (bq - aq) / (bq + aq)


def top_level_ofi(prev_bid, prev_ask, bid, ask) -> float:
    """Order flow imbalance between two top-of-book states (Cont, Kukanov, Stoikov 2014).

    Each argument is (price, qty). Positive values mean net buying pressure.
    """
    (pb, pbq), (pa, paq) = prev_bid, prev_ask
    (b, bq), (a, aq) = bid, ask
    e_bid = (bq if b >= pb else 0.0) - (pbq if b <= pb else 0.0)
    e_ask = (aq if a <= pa else 0.0) - (paq if a >= pa else 0.0)
    return e_bid - e_ask
