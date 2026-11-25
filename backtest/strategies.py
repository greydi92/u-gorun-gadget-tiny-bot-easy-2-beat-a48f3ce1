"""Strategy variants, each a decide(sim, k, closes, universe) function."""
from engine import ema_series, sma_series, rsi_series, SYMS, CAPITAL

_cache = {}
def ema(sym, span, closes):
    key = (sym, span)
    if key not in _cache:
        _cache[key] = ema_series(closes[sym], span)
    return _cache[key]

def rsi(sym, span, closes):
    key = ("rsi", sym, span)
    if key not in _cache:
        _cache[key] = rsi_series(closes[sym], span)
    return _cache[key]

def sma(sym, span, closes):
    key = ("sma", sym, span)
    if key not in _cache:
        _cache[key] = sma_series(closes[sym], span)
    return _cache[key]

def make_ema_cross(fast, slow, roi=None, stop=None):
    def decide(sim, k, closes, universe):
        eq = sim.equity(k)
        slot = eq / min(len(universe), 10)
        for sym in universe:
            ef, es = ema(sym, fast, closes), ema(sym, slow, closes)
            if ef[k] is None or es[k] is None or ef[k-1] is None or es[k-1] is None:
                continue
            held = sym in sim.pos
            cross_up = ef[k] > es[k] and ef[k-1] <= es[k-1]
            cross_dn = ef[k] < es[k] and ef[k-1] >= es[k-1]
            if held:
                qty, cost = sim.pos[sym]
                val = qty * closes[sym][k]
                if cross_dn or (roi and val >= roi * cost) or (stop and val <= stop * cost):
                    sim.sell(sym, k)
            elif cross_up:
                amt = min(slot, 0.25 * eq, sim.cash)
                if amt >= 1:
                    sim.buy(sym, amt, k)
    return decide

def make_momentum(topn=3, lookback=24, period=24):
    state = {"next": lookback, "entering": None}
    def decide(sim, k, closes, universe):
        if state["entering"] is not None:
            # buys queued after sells filled
            eq = sim.equity(k)
            n = len(state["entering"])
            for sym in state["entering"]:
                amt = min(sim.cash / max(n, 1), 0.25 * eq, sim.cash)
                if amt >= 1 and sym not in sim.pos:
                    sim.buy(sym, amt, k)
            state["entering"] = None
            return
        if k < state["next"]:
            return
        state["next"] += period
        ranked = []
        for sym in universe:
            if k - lookback >= 0 and closes[sym][k - lookback] > 0:
                ranked.append((closes[sym][k] / closes[sym][k - lookback], sym))
        ranked.sort(reverse=True)
        target = [s for _, s in ranked[:topn]]
        sold = False
        for sym in list(sim.pos):
            if sym not in target:
                sim.sell(sym, k); sold = True
        entering = [s for s in target if s not in sim.pos]
        if sold and entering:
            state["entering"] = entering  # buy next bar with proceeds
        elif entering:
            eq = sim.equity(k)
            for sym in entering:
                amt = min(sim.cash / len(entering), 0.25 * eq, sim.cash)
                if amt >= 1:
                    sim.buy(sym, amt, k)
    return decide

def make_rsi_meanrev(lo=30, hi=70, span=14):
    def decide(sim, k, closes, universe):
        eq = sim.equity(k)
        slot = eq / min(len(universe), 10)
        for sym in universe:
            r = rsi(sym, span, closes)
            if r[k] is None:
                continue
            held = sym in sim.pos
            if held and r[k] > hi:
                sim.sell(sym, k)
            elif not held and r[k] < lo:
                amt = min(slot, 0.25 * eq, sim.cash)
                if amt >= 1:
                    sim.buy(sym, amt, k)
    return decide

def make_bollinger(span=20, mult=2.0):
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
            if held and c >= hi:
                sim.sell(sym, k)
            elif not held and c <= lo:
                amt = min(slot, 0.25 * eq, sim.cash)
                if amt >= 1:
                    sim.buy(sym, amt, k)
    return decide

def make_trend_filter(fast=8, slow=21, mom_lb=24, mom_min=0.0):
    """EMA cross only when trailing momentum is positive (avoids buying falling knives)."""
    def decide(sim, k, closes, universe):
        eq = sim.equity(k)
        slot = eq / min(len(universe), 10)
        for sym in universe:
            ef, es = ema(sym, fast, closes), ema(sym, slow, closes)
            if ef[k] is None or es[k] is None or ef[k-1] is None or es[k-1] is None:
                continue
            mom = closes[sym][k] / closes[sym][k - mom_lb] - 1 if k >= mom_lb else 0
            held = sym in sim.pos
            cross_up = ef[k] > es[k] and ef[k-1] <= es[k-1]
            cross_dn = ef[k] < es[k] and ef[k-1] >= es[k-1]
            if held and cross_dn:
                sim.sell(sym, k)
            elif not held and cross_up and mom > mom_min:
                amt = min(slot, 0.25 * eq, sim.cash)
                if amt >= 1:
                    sim.buy(sym, amt, k)
    return decide

def make_donchian(n=24, exit_n=12):
    def decide(sim, k, closes, universe):
        eq = sim.equity(k)
        slot = eq / min(len(universe), 10)
        for sym in universe:
            if k < n:
                continue
            hi = max(closes[sym][k - n:k])
            lo = min(closes[sym][k - exit_n:k])
            c = closes[sym][k]
            held = sym in sim.pos
            if held and c <= lo:
                sim.sell(sym, k)
            elif not held and c >= hi:
                amt = min(slot, 0.25 * eq, sim.cash)
                if amt >= 1:
                    sim.buy(sym, amt, k)
    return decide

_bh_done = {"v": False}
def buy_and_hold(sim, k, closes, universe):
    if _bh_done["v"]:
        return
    _bh_done["v"] = True
    eq = sim.equity(k)
    n = min(len(universe), 10)
    for sym in universe[:n]:
        amt = min(eq / n, 0.25 * eq, sim.cash)
        if amt >= 1:
            sim.buy(sym, amt, k)

def hold_cash(sim, k, closes, universe):
    pass
