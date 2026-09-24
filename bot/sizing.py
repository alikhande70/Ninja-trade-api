"""Balance-based position sizing and account-level risk guards.

Reference implementation of the rules the MT5 Expert Advisor applies
(mt5/Include/RiskSizing.mqh mirrors this file). All default numbers are
proposed settings, not validated values; they are revisited after the
strategy has been tested with real costs.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

_EPS = 1e-9


@dataclass(frozen=True)
class SymbolSpec:
    tick_size: float          # SYMBOL_TRADE_TICK_SIZE
    tick_value_loss: float    # SYMBOL_TRADE_TICK_VALUE_LOSS, account currency per tick per 1.0 lot
    volume_min: float         # SYMBOL_VOLUME_MIN
    volume_step: float        # SYMBOL_VOLUME_STEP
    volume_max: float         # SYMBOL_VOLUME_MAX
    commission_per_lot_rt: float = 0.0  # round-turn commission per 1.0 lot, account currency


@dataclass(frozen=True)
class SizingResult:
    ok: bool
    lots: float
    base: float
    risk_budget: float
    actual_risk: float
    loss_per_lot: float
    reason: str


def _steps_down(value: float, step: float) -> int:
    return int(math.floor(value / step + _EPS))


def _step_decimals(step: float) -> int:
    text = f"{step:.10f}".rstrip("0")
    return len(text.split(".")[1]) if "." in text else 0


def drawdown_throttle(equity: float, peak_equity: float) -> float:
    """Risk multiplier from drawdown against the equity high-water mark.

    Proposed setting: full risk below 10% drawdown, half from 10%, quarter
    from 15%, and 0 (halt) from 20%.
    """
    if peak_equity <= 0:
        return 0.0
    dd = 1.0 - equity / peak_equity + _EPS  # exactly 10% must count as 10%, not 9.999...%
    if dd >= 0.20:
        return 0.0
    if dd >= 0.15:
        return 0.25
    if dd >= 0.10:
        return 0.5
    return 1.0


def compute_lots(
    *,
    balance: float,
    equity: float,
    risk_pct: float,
    sl_distance: float,
    spec: SymbolSpec,
    ai_multiplier: float = 1.0,
    dd_multiplier: float = 1.0,
    free_margin: float | None = None,
    margin_per_lot: float | None = None,
    max_margin_fraction: float = 0.30,
) -> SizingResult:
    """Lot size so that a stop-out loses at most risk_pct of min(balance, equity).

    Always rounds down to the broker's volume step. Never substitutes the
    minimum volume when the correct size is smaller: the trade is refused.
    """
    base = min(balance, equity)

    def reject(reason: str, budget: float = 0.0, lpl: float = 0.0) -> SizingResult:
        return SizingResult(False, 0.0, base, budget, 0.0, lpl, reason)

    if base <= 0:
        return reject("no_funds")
    if sl_distance <= 0:
        return reject("invalid_stop")
    if spec.tick_size <= 0 or spec.tick_value_loss <= 0 or spec.volume_step <= 0:
        return reject("invalid_symbol_spec")
    if not 0 < risk_pct <= 5:
        return reject("invalid_risk_pct")

    ai = min(max(ai_multiplier, 0.0), 1.0)
    dd = min(max(dd_multiplier, 0.0), 1.0)
    budget = base * risk_pct / 100.0 * ai * dd
    loss_per_lot = (sl_distance / spec.tick_size) * spec.tick_value_loss + spec.commission_per_lot_rt
    if ai == 0:
        return reject("ai_blocked", budget, loss_per_lot)
    if dd == 0:
        return reject("drawdown_halt", budget, loss_per_lot)

    steps = _steps_down(budget / loss_per_lot, spec.volume_step)
    steps = min(steps, _steps_down(spec.volume_max, spec.volume_step))

    if margin_per_lot is not None and free_margin is not None:
        if margin_per_lot <= 0:
            return reject("invalid_margin", budget, loss_per_lot)
        by_margin = _steps_down(free_margin * max_margin_fraction / margin_per_lot, spec.volume_step)
        if by_margin < steps:
            steps = by_margin
            if steps * spec.volume_step + _EPS < spec.volume_min:
                return reject("insufficient_margin", budget, loss_per_lot)

    lots = round(steps * spec.volume_step, _step_decimals(spec.volume_step))
    if lots + _EPS < spec.volume_min:
        return reject("below_min_volume", budget, loss_per_lot)

    actual = lots * loss_per_lot
    return SizingResult(True, lots, base, budget, actual, loss_per_lot, "ok")


@dataclass
class RiskGuard:
    """Daily / weekly / total loss limits on equity (floating loss included).

    Proposed settings: 2% daily, 5% weekly, 20% from peak. Deposits and
    withdrawals must be reported through on_cash_flow so that they are not
    mistaken for profit or loss.
    """

    day_start_equity: float
    week_start_equity: float
    peak_equity: float
    daily_limit: float = 0.02
    weekly_limit: float = 0.05
    total_limit: float = 0.20

    def on_new_day(self, equity: float) -> None:
        self.day_start_equity = equity

    def on_new_week(self, equity: float) -> None:
        self.week_start_equity = equity

    def on_cash_flow(self, amount: float) -> None:
        self.day_start_equity += amount
        self.week_start_equity += amount
        self.peak_equity = max(self.peak_equity + amount, 0.0)

    def update(self, equity: float) -> str:
        """Returns 'ok', 'daily_lock', 'weekly_lock' or 'total_halt'."""
        self.peak_equity = max(self.peak_equity, equity)
        if self.peak_equity > 0 and equity <= self.peak_equity * (1 - self.total_limit) + _EPS:
            return "total_halt"
        if self.week_start_equity > 0 and equity <= self.week_start_equity * (1 - self.weekly_limit) + _EPS:
            return "weekly_lock"
        if self.day_start_equity > 0 and equity <= self.day_start_equity * (1 - self.daily_limit) + _EPS:
            return "daily_lock"
        return "ok"
