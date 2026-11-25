// Bollinger Dip Bot — mean-reversion on hourly Solana bars.
//
// Strategy (chosen by backtesting 20+ variants on the kit's dev window):
//   Per symbol, over the last 16 closes, compute the mean and the population
//   standard deviation. BUY when the close touches or drops below the lower
//   band (mean - 2*sd); SELL the whole position when the close reaches or
//   passes the upper band (mean + 2*sd). Long only, no leverage, no shorts.
//
// Why this won the backtest (dev window 2026-10-29..2026-11-03, 136 hourly
// bars, $10,000 capital, 10 bps fee + 5 bps slippage + pool impact):
//   buy-and-hold (equal weight, all 7 symbols)  -$869.35  (-8.69%)
//   EMA cross 8/21                              -$151.55  (-1.52%)
//   cross-sectional momentum top-3 24h           -$258.67  (-2.59%)
//   RSI mean-reversion 30/70                     -$55.46  (-0.55%)
//   Bollinger 20/2.0                             +$11.99  (+0.12%)
//   Bollinger 24/2.0                            +$279.65  (+2.80%)
//   Bollinger 16/2.0 (THIS BOT)                 +$59.85  (+0.60%)
//   The 16-bar window was picked over 24 because it is the most robust
//   across regimes, not the best on the full window alone:
//     first half (hard downtrend):  +$162.74 vs buy-and-hold -$660.26
//     second half (flat / slight down): -$80.15 vs buy-and-hold -$221.42
//     reversed series (synthetic uptrend): +$734.32 vs buy-and-hold +$641.50
//   i.e. it beats buy-and-hold in down, flat AND up regimes, with max
//   drawdown 3.77% (guardrail: 25%) and 30 trades (guardrail: min 8).
//   Shorter windows (12/14) capture uptrends even better but go negative
//   on the full window; longer windows (24/28) need too much warm-up for a
//   72-bar final window and fade in flat markets. 16 bars is the sweet spot.
//
// Sizing: equity / n per symbol, n = min(universe, max open positions),
// capped by the 25% max-weight cap and the cash on hand. Buys and sells are
// decided on a bar's close and fill at the next bar's open (1-bar latency).
// Slippage is capped at 100 bps past the close, so an order into a
// liquidity gap is refused and retried on the next bar while its signal
// still holds, instead of filling for almost nothing.
//
// Deterministic: pure float64 math on closes only. No clock, no environment,
// no randomness, no network, no outside data. Never throws: any unexpected
// error returns no orders for that batch (diagnostics go to stderr).

import { BPS, runBars, type BarsState, type BuyInput, type OrderInput, type SellInput } from './vendor/makefun-bars.ts';

/** Bollinger window (bars) and band width (standard deviations). */
const BB_BARS = 16;
const BB_MULT = 2;
/** Max slippage past the close an order tolerates (100 bps = 1%). */
const MAX_SLIPPAGE_BPS = 100;

/** Each symbol's closes so far, oldest first. */
const closes = new Map<string, number[]>();

/** Bollinger bands of the last BB_BARS closes, or null without enough history. */
function bands(history: number[]): { mean: number; lower: number; upper: number } | null {
  if (history.length < BB_BARS) return null;
  const window = history.slice(-BB_BARS);
  let sum = 0;
  for (const c of window) sum += c;
  const mean = sum / BB_BARS;
  let sq = 0;
  for (const c of window) sq += (c - mean) * (c - mean);
  const sd = Math.sqrt(sq / BB_BARS);
  return { mean, lower: mean - BB_MULT * sd, upper: mean + BB_MULT * sd };
}

function onBatch(state: BarsState): OrderInput[] {
  try {
    return decide(state);
  } catch (err) {
    console.error(`batch ${state.seq}: ${err instanceof Error ? err.message : String(err)}`);
    return [];
  }
}

function decide(state: BarsState): OrderInput[] {
  // While warming up every order would be rejected; keep seeding history.
  if (state.warmingUp) return [];
  const { caps, fees } = state.hello;
  const symbols = state.hello.symbols.map((s) => s.symbol);
  const n = Math.min(symbols.length, caps.max_open_positions, caps.max_orders_per_bar);
  const slot = state.equity / BigInt(n);
  const orders: OrderInput[] = [];
  let spent = 0n;

  for (const symbol of symbols) {
    const close = state.close(symbol);
    if (close === null) continue;
    const history = closes.get(symbol) ?? [];
    const band = bands(history);
    if (band === null) continue;
    const held = state.positions.get(symbol);
    const price = Number(close);

    if (held) {
      // Exit the whole position at the upper band; retry next bar if refused.
      if (price >= band.upper) {
        orders.push({ side: 'sell', symbol, qty: held.qty, max_slippage_bps: MAX_SLIPPAGE_BPS } satisfies SellInput);
      }
    } else if (price <= band.lower) {
      // Dip-buy one slot, capped by the weight cap and the cash left.
      const byWeight = state.weightRoom(symbol);
      let amount = slot < byWeight ? slot : byWeight;
      const cashLeft = state.cash - spent;
      if (amount > cashLeft) amount = cashLeft;
      if (amount >= BigInt(fees.min_notional_quote_units)) {
        orders.push({ side: 'buy', symbol, notional_quote_units: amount, max_slippage_bps: MAX_SLIPPAGE_BPS } satisfies BuyInput);
        spent += amount;
      }
    }
    if (orders.length >= caps.max_orders_per_bar) break;
  }
  return orders;
}

await runBars({
  onBatch(state) {
    // Record every symbol's close first, so the bands read this bar too.
    for (const { symbol } of state.hello.symbols) {
      const close = state.close(symbol);
      if (close === null) continue;
      const history = closes.get(symbol) ?? [];
      history.push(Number(close));
      closes.set(symbol, history);
    }
    return onBatch(state);
  },
});
