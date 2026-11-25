"""Round 4: partial exits, breakout re-entry, sleeve combos."""
from engine import ema_series, sma_series, SYMS, CAPITAL
import strategies as S

def _ema(sym, span, closes):
    return S._cache.setdefault((sym, span), ema_series(closes[sym], span))

def make_bb_partial(span=20, mult=2.0, first_frac=0.5):
    """Sell first_frac at upper band; sell the rest when close falls below the middle."""
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
                # full position still at cost basis? partial already taken if qty < slot-ish:
                # track via cost: if we already sold half, cost was halved too; use a marker on sim
                tag = getattr(sim, "_bb_partial", None)
                if tag is None:
                    sim._bb_partial = set()
                if sym in sim._bb_partial:
                    if c < m:
                        sim.sell(sym, k)
                        sim._bb_partial.discard(sym)
                elif c >= hi:
                    sim.sell(sym, k, frac=first_frac)
                    sim._bb_partial.add(sym)
            elif not held and c <= lo:
                amt = min(slot, 0.25 * eq, sim.cash)
                if amt >= 1:
                    sim.buy(sym, amt, k)
    return decide

def make_bb_breakout(span=20, mult=2.0):
    """Buy lower band; sell upper band; but re-buy on a close above the upper band
    (breakout) and hold until close back below the middle."""
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
            mode = getattr(sim, "_bb_mode", None)
            if mode is None:
                sim._bb_mode = {}
            if held:
                if sim._bb_mode.get(sym) == "ride":
                    if c < m:
                        sim.sell(sym, k)
                        sim._bb_mode.pop(sym, None)
                elif c >= hi:
                    sim.sell(sym, k)
                    sim._bb_mode.pop(sym, None)
            else:
                if c <= lo:
                    amt = min(slot, 0.25 * eq, sim.cash)
                    if amt >= 1:
                        sim.buy(sym, amt, k)
                        sim._bb_mode[sym] = "dip"
                elif c >= hi and k >= span + 1 and closes[sym][k-1] <= hi:
                    # fresh breakout above the band: ride it
                    amt = min(slot, 0.25 * eq, sim.cash)
                    if amt >= 1:
                        sim.buy(sym, amt, k)
                        sim._bb_mode[sym] = "ride"
    return decide
