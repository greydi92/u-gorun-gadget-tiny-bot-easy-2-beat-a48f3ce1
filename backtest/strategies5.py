"""Round 5 (iterate R2, FINAL): robustness checks NOT covered in R1.

R1 already tested: parameter sweep (24/2.0 rejected as overfit), partial
exit 50% (rejected, only +$6.75). This round tests NEW angles:
  1. Fee/slippage sensitivity: 2x and 3x the base costs (10bps fee + 5bps
     slip) for Bollinger 16/2.0 and for buy-and-hold.
  2. Quarter splits: 4 x 34-bar segments, 16/2.0 vs buy-and-hold in each.
  3. One new strategy variant: Bollinger 16/2.0 + 8% stop-loss on cost basis.
"""
import engine
from engine import SYMS
import strategies as S


def make_bb_stoploss(span=16, mult=2.0, stop=0.92):
    """Bollinger dip bot, but cut a position if its value falls to `stop`
    of its cost basis (protects against a dip that keeps dipping)."""
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
                if c >= hi or val <= stop * cost:
                    sim.sell(sym, k)
            elif not held and c <= lo:
                amt = min(slot, 0.25 * eq, sim.cash)
                if amt >= 1:
                    sim.buy(sym, amt, k)
    return decide


def reset_bh():
    S._bh_done["v"] = False


def run():
    bb = S.make_bollinger(16, 2.0)
    results = []

    # --- 1. Fee / slippage sensitivity (full window) ---
    for label, fee, slip in [("base 10bp+5bp", 0.0010, 0.0005),
                             ("2x   20bp+10bp", 0.0020, 0.0010),
                             ("3x   30bp+15bp", 0.0030, 0.0015)]:
        engine.FEE, engine.SLIP = fee, slip
        r = engine.run_strategy(bb, f"BB 16/2.0 [{label}]")
        reset_bh()
        rb = engine.run_strategy(S.buy_and_hold, f"B&H [{label}]")
        results.append((r, rb))
        print(f"{r['name']:28s} PnL {r['pnl']:9.2f}  trades {r['trades']:3d}  maxDD {r['maxdd%']:5.2f}%  | "
              f"B&H PnL {rb['pnl']:9.2f}  margin {r['pnl'] - rb['pnl']:+9.2f}")
    engine.FEE, engine.SLIP = 0.0010, 0.0005  # restore base

    # --- 2. Quarter splits (34 bars each), base costs ---
    print("\nQuarter splits (base costs):")
    for i, (k0, k1) in enumerate([(0, 33), (34, 67), (68, 101), (102, 134)]):
        r = engine.run_strategy(bb, f"BB 16/2.0 Q{i+1}", k0=k0, k1=k1)
        reset_bh()
        rb = engine.run_strategy(S.buy_and_hold, f"B&H Q{i+1}", k0=k0, k1=k1)
        print(f"Q{i+1} bars {k0:3d}-{k1:3d}: BB PnL {r['pnl']:9.2f} trades {r['trades']:3d} | "
              f"B&H PnL {rb['pnl']:9.2f} | margin {r['pnl'] - rb['pnl']:+9.2f}")

    # --- 3. Stop-loss variant, full window, base costs ---
    print("\nStop-loss variant (full window, base costs):")
    for stop in (0.92, 0.95):
        r = engine.run_strategy(make_bb_stoploss(16, 2.0, stop),
                                f"BB 16/2.0 + stop {stop}")
        print(f"BB 16/2.0 + stop-loss {stop}: PnL {r['pnl']:9.2f}  trades {r['trades']:3d}  "
              f"maxDD {r['maxdd%']:5.2f}%  (base BB 16/2.0: +59.85, 30 trades, 3.77%)")


if __name__ == "__main__":
    run()
