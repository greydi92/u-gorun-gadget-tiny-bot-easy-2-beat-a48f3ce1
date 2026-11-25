"""Local backtester for the bars-replay/v1 dev window.

Replicates the harness market model closely enough for strategy selection:
- orders decided on bar k fill at bar k+1 open (latency 1)
- fee 10 bps, modelled slippage 5 bps, constant-product impact vs pool depth
- max weight 25% of equity per symbol, max 10 positions, min notional $1
- positions flattened at the last close; equity marked at closes; max DD tracked
Prices in USD floats; notional in USDC.
"""
import gzip, json, math, os, sys

KIT = "/home/hatch/workspace/kerjaan/makefun/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1-kit/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1-kit"
CAPITAL = 10000.0
FEE = 0.0010
SLIP = 0.0005
MAXW = 0.25

def load_bars():
    man = json.load(open(f"{KIT}/dataset/manifest.json"))
    data = {}
    for s in man["symbols"]:
        sym = s["symbol"]
        rows = []
        with gzip.open(f"{KIT}/dataset/bars/{sym}.ndjson.gz", "rt") as f:
            for line in f:
                b = json.loads(line)
                ps = s["price_scale"]
                rows.append({
                    "t": b["t"],
                    "o": int(b["o"]) / 10 ** ps,
                    "h": int(b["h"]) / 10 ** ps,
                    "l": int(b["l"]) / 10 ** ps,
                    "c": int(b["c"]) / 10 ** ps,
                    "o_depth": [int(d) / 1e6 for d in b["o_depth"]],  # USDC per hop
                    "c_depth": [int(d) / 1e6 for d in b["c_depth"]],
                })
        data[sym] = rows
    return data

DATA = load_bars()
SYMS = sorted(DATA)
N = len(DATA["SOL"])

def impact(depth, amount_usd):
    """constant-product impact factor M-1 for a trade of amount_usd against depths."""
    m = 0.0
    for d in depth:
        m += amount_usd / d if d > 0 else 0.0
    return m

class Sim:
    def __init__(self):
        self.cash = CAPITAL
        self.pos = {}  # sym -> (qty, cost_usd)
        self.trades = 0
        self.peak = CAPITAL
        self.maxdd = 0.0
        self.equity_hist = []

    def equity(self, k):
        e = self.cash
        for sym, (qty, _) in self.pos.items():
            e += qty * DATA[sym][k]["c"]
        return e

    def mark(self, k):
        e = self.equity(k)
        self.equity_hist.append(e)
        if e > self.peak:
            self.peak = e
        dd = (self.peak - e) / self.peak if self.peak else 0
        if dd > self.maxdd:
            self.maxdd = dd
        return e

    def buy(self, sym, notional, k):
        """decided on bar k, fills at bar k+1 open. Returns filled qty or 0."""
        if k + 1 >= N or notional < 1.0:
            return 0.0
        bar = DATA[sym][k + 1]
        depth = bar["o_depth"]
        imp = impact(depth, notional)
        px = bar["o"] * (1 + SLIP + imp)
        qty = notional * (1 - FEE) / px
        room = MAXW * self.equity(k) - self.pos.get(sym, (0, 0))[0] * DATA[sym][k]["c"]
        if qty * px > room:
            qty = room / px
        if qty * px < 1.0:
            return 0.0
        spend = qty * px / (1 - FEE)  # notional incl fee handling: keep simple
        spend = qty * bar["o"] * (1 + SLIP + imp) / (1 - FEE)
        if spend > self.cash:
            qty = self.cash * (1 - FEE) / px
            spend = self.cash
        if qty <= 0:
            return 0.0
        self.cash -= spend
        q0, c0 = self.pos.get(sym, (0.0, 0.0))
        self.pos[sym] = (q0 + qty, c0 + spend)
        self.trades += 1
        return qty

    def sell(self, sym, k, frac=1.0):
        if sym not in self.pos or k + 1 >= N:
            return 0.0
        qty, cost = self.pos[sym]
        qty *= frac
        if qty <= 0:
            return 0.0
        bar = DATA[sym][k + 1]
        depth = bar["o_depth"]
        amt = qty * bar["o"]
        imp = impact(depth, amt)
        px = bar["o"] * (1 - SLIP - imp)
        proceeds = qty * px * (1 - FEE)
        self.cash += proceeds
        if frac >= 1.0:
            del self.pos[sym]
        else:
            self.pos[sym] = (self.pos[sym][0] - qty, cost * (1 - frac))
        self.trades += 1
        return proceeds

    def flatten(self, k=None):
        k = N - 1 if k is None else k
        for sym in list(self.pos):
            qty, _ = self.pos[sym]
            px = DATA[sym][k]["c"]
            imp = impact(DATA[sym][k]["c_depth"], qty * px)
            self.cash += qty * px * (1 - SLIP - imp) * (1 - FEE)
            self.trades += 1
        self.pos = {}

def ema_series(closes, span):
    out = []
    k = 2.0 / (span + 1)
    e = None
    for i, c in enumerate(closes):
        if e is None:
            if i + 1 >= span:
                e = sum(closes[i - span + 1:i + 1]) / span
            else:
                out.append(None)
                continue
        else:
            e = c * k + e * (1 - k)
        out.append(e)
    return out

def sma_series(closes, span):
    return [sum(closes[max(0, i - span + 1):i + 1]) / min(span, i + 1) if i + 1 >= span else None
            for i in range(len(closes))]

def rsi_series(closes, span=14):
    out = [None] * len(closes)
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0)); losses.append(max(-d, 0))
        if i >= span:
            ag = sum(gains[-span:]) / span
            al = sum(losses[-span:]) / span
            out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out

def run_strategy(decide, name, universe=None, k0=0, k1=None):
    """decide(sim, k, hist) -> None; hist holds per-symbol closes up to k."""
    universe = universe or SYMS
    sim = Sim()
    closes = {s: [b["c"] for b in DATA[s]] for s in universe}
    k1 = k1 or (N - 2)  # last decidable bar (fills at k+1)
    for k in range(k0, k1 + 1):
        decide(sim, k, closes, universe)
        sim.mark(k)
    sim.flatten(k1)
    final = sim.cash
    pnl = final - CAPITAL
    return {"name": name, "pnl": pnl, "ret%": 100 * pnl / CAPITAL,
            "trades": sim.trades, "maxdd%": 100 * sim.maxdd,
            "final": final}

def report(results):
    print(f"{'strategy':34s} {'PnL $':>9s} {'ret%':>7s} {'trades':>6s} {'maxDD%':>7s}")
    for r in sorted(results, key=lambda x: -x["pnl"]):
        print(f"{r['name']:34s} {r['pnl']:9.2f} {r['ret%']:7.2f} {r['trades']:6d} {r['maxdd%']:7.2f}")
