"""Round 3: Bollinger refinements + slow trend filter."""
from engine import ema_series, sma_series, SYMS, CAPITAL
import strategies as S

def _ema(sym, span, closes):
    return S._cache.setdefault((sym, span), ema_series(closes[sym], span))

def _sma(sym, span, closes):
    return S._cache.setdefault(("sma", sym, span), sma_series(closes[sym], span))

def make_bb_stop(span=20, mult=2.0, stop=0.05, tp_band="upper"):
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
                qty, cost = sim.pos[sym]
                val = qty * c
                exit_px = hi if tp_band == "upper" else m
                if c >= exit_px or val <= (1 - stop) * cost:
                    sim.sell(sym, k)
            elif not held and c <= lo:
                amt = min(slot, 0.25 * eq, sim.cash)
                if amt >= 1:
                    sim.buy(sym, amt, k)
    return decide

def make_bb_trendfilter(span=20, mult=2.0, trend_span=21):
    """Buy Bollinger dips only when close is above the slow EMA (uptrend/flat dips)."""
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
            es = _ema(sym, trend_span, closes)
            up = es[k] is not None and c >= es[k]
            held = sym in sim.pos
            if held and c >= hi:
                sim.sell(sym, k)
            elif not held and c <= lo and up:
                amt = min(slot, 0.25 * eq, sim.cash)
                if amt >= 1:
                    sim.buy(sym, amt, k)
    return decide

def make_bb_mid_exit(span=20, mult=2.0):
    """Buy lower band, exit at the middle (mean) — faster turnover."""
    def decide(sim, k, closes, universe):
        eq = sim.equity(k)
        slot = eq / min(len(universe), 10)
        for sym in universe:
            if k < span:
                continue
            w = closes[sym][k - span + 1:k + 1]
            m = sum(w) / span
            sd = (sum((x - m) ** 2 for x in w) / span) ** 0.5
            lo = m - mult * sd
            c = closes[sym][k]
            held = sym in sim.pos
            if held and c >= m:
                sim.sell(sym, k)
            elif not held and c <= lo:
                amt = min(slot, 0.25 * eq, sim.cash)
                if amt >= 1:
                    sim.buy(sym, amt, k)
    return decide

def make_sma_trend(span=24):
    """Hold a symbol only while its close is above SMA(span); hourly rebalance."""
    def decide(sim, k, closes, universe):
        eq = sim.equity(k)
        slot = eq / min(len(universe), 10)
        for sym in universe:
            sm = _sma(sym, span, closes)
            if sm[k] is None:
                continue
            c = closes[sym][k]
            held = sym in sim.pos
            if held and c < sm[k]:
                sim.sell(sym, k)
            elif not held and c > sm[k]:
                amt = min(slot, 0.25 * eq, sim.cash)
                if amt >= 1:
                    sim.buy(sym, amt, k)
    return decide
