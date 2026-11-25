"""Round 2: hybrids, exits, Bollinger params, universe subsets."""
from engine import ema_series, sma_series, rsi_series, SYMS, CAPITAL
import strategies as S

def _ema(sym, span, closes):
    return S._cache.setdefault((sym, span), ema_series(closes[sym], span))

def make_bollinger2(span=20, mult=2.0, exit_on_ema=False):
    def decide(sim, k, closes, universe):
        eq = sim.equity(k)
        slot = eq / min(len(universe), 10)
        for sym in universe:
            if k < span:
                continue
            w = closes[sym][k - span + 1:k + 1]
            m = sum(w) / span
            sd = (sum((x - m) ** 2 for x in w) / span) ** 0.5
            lo, hi = m - mult * sd, m + mult * sd
            c = closes[sym][k]
            held = sym in sim.pos
            if held:
                ef = _ema(sym, 8, closes)
                cross_dn = ef[k] is not None and ef[k-1] is not None and c < ef[k] and c < m
                if c >= hi or (exit_on_ema and cross_dn):
                    sim.sell(sym, k)
            elif not held and c <= lo:
                amt = min(slot, 0.25 * eq, sim.cash)
                if amt >= 1:
                    sim.buy(sym, amt, k)
    return decide

def make_ema_tp(fast=8, slow=21, tp=0.10, trail=0.05):
    """EMA cross entry; exit on cross-down, take-profit, or trailing stop from peak."""
    peaks = {}
    def decide(sim, k, closes, universe):
        eq = sim.equity(k)
        slot = eq / min(len(universe), 10)
        for sym in universe:
            ef, es = _ema(sym, fast, closes), _ema(sym, slow, closes)
            if ef[k] is None or es[k] is None or ef[k-1] is None or es[k-1] is None:
                continue
            c = closes[sym][k]
            held = sym in sim.pos
            cross_up = ef[k] > es[k] and ef[k-1] <= es[k-1]
            cross_dn = ef[k] < es[k] and ef[k-1] >= es[k-1]
            if held:
                peaks[sym] = max(peaks.get(sym, c), c)
                qty, cost = sim.pos[sym]
                val = qty * c
                if cross_dn or val >= (1 + tp) * cost or c <= peaks[sym] * (1 - trail):
                    sim.sell(sym, k)
                    peaks.pop(sym, None)
            elif cross_up:
                amt = min(slot, 0.25 * eq, sim.cash)
                if amt >= 1:
                    sim.buy(sym, amt, k)
                    peaks[sym] = c
    return decide

def make_hybrid(fast=8, slow=21, bb_span=20, bb_mult=2.0):
    """Enter on EMA cross-up OR Bollinger dip; exit on EMA cross-down or Bollinger upper band."""
    def decide(sim, k, closes, universe):
        eq = sim.equity(k)
        slot = eq / min(len(universe), 10)
        for sym in universe:
            ef, es = _ema(sym, fast, closes), _ema(sym, slow, closes)
            if ef[k] is None or es[k] is None or ef[k-1] is None or es[k-1] is None:
                continue
            c = closes[sym][k]
            w = closes[sym][k - bb_span + 1:k + 1] if k >= bb_span else None
            if w:
                m = sum(w) / bb_span
                sd = (sum((x - m) ** 2 for x in w) / bb_span) ** 0.5
                lo, hi = m - bb_mult * sd, m + bb_mult * sd
            else:
                lo = hi = None
            held = sym in sim.pos
            cross_up = ef[k] > es[k] and ef[k-1] <= es[k-1]
            cross_dn = ef[k] < es[k] and ef[k-1] >= es[k-1]
            if held:
                if cross_dn or (hi is not None and c >= hi):
                    sim.sell(sym, k)
            elif cross_up or (lo is not None and c <= lo):
                amt = min(slot, 0.25 * eq, sim.cash)
                if amt >= 1:
                    sim.buy(sym, amt, k)
    return decide

def make_fast_exit(fast=5, slow=13):
    """EMA cross entry; exit the moment close drops below fast EMA (fast exit)."""
    def decide(sim, k, closes, universe):
        eq = sim.equity(k)
        slot = eq / min(len(universe), 10)
        for sym in universe:
            ef, es = _ema(sym, fast, closes), _ema(sym, slow, closes)
            if ef[k] is None or es[k] is None or ef[k-1] is None or es[k-1] is None:
                continue
            c = closes[sym][k]
            held = sym in sim.pos
            cross_up = ef[k] > es[k] and ef[k-1] <= es[k-1]
            if held and c < ef[k]:
                sim.sell(sym, k)
            elif not held and cross_up:
                amt = min(slot, 0.25 * eq, sim.cash)
                if amt >= 1:
                    sim.buy(sym, amt, k)
    return decide
