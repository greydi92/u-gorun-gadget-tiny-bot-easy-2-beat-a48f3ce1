[![make.fun](https://make.fun/badge/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1.svg)](https://make.fun/bounty/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1)
[![rank](https://make.fun/badge/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1/greydi92/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1/rank.svg)](https://make.fun/bounty/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1)
[![reward](https://make.fun/badge/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1/greydi92/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1/reward.svg)](https://make.fun/bounty/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1)


Join make.fun with referral code `qgn48q27`: https://make.fun/r/qgn48q27


# Bollinger Dip Bot


A tiny mean-reversion bot for [Tiny Bot, Easy $2: Beat Buy-and-Hold on Solana](https://make.fun/bounty/u-gorun-gadget-tiny-bot-easy-2-beat-a48f3ce1).


**Strategy:** per symbol, over the last 16 hourly closes, buy when the close
touches the lower Bollinger band (mean − 2σ) and sell the whole position when
it reaches the upper band (mean + 2σ). Long only, one slot of equity/n per
symbol, capped at the 25% max-weight cap, 100 bps slippage cap. Deterministic,
no network, no outside data.


**Backtest (kit dev window, 2026-10-29–2026-11-03, 136 hourly bars, $10,000,
10 bps fee + 5 bps slippage + pool impact):**


| strategy | net PnL | vs buy-and-hold |
|---|---|---|
| buy-and-hold (equal, all 7) | −$869.35 | — |
| EMA cross 8/21 | −$151.55 | +$717.80 |
| momentum top-3, 24h | −$258.67 | +$610.68 |
| RSI mean-reversion 30/70 | −$55.46 | +$813.89 |
| Bollinger 20/2.0 | +$11.99 | +$881.34 |
| **Bollinger 16/2.0 (this bot)** | **+$59.85** | **+$929.20** |


The 16-bar window was picked for robustness across regimes, not for the best
single-window number: first half (hard downtrend) +$162.74 vs buy-and-hold
−$660.26; second half (flat) −$80.15 vs −$221.42; reversed series (synthetic
uptrend) +$734.32 vs buy-and-hold +$641.50 — it beats buy-and-hold in down,
flat, and up markets. Max drawdown 3.77% (guardrail 25%), 30 trades
(guardrail min 8).


**Run:** `node main.ts` (Node 22+). The grader runs it as `node /bot/main.ts`.
`vendor/makefun-bars.ts` is the kit's own bars-replay/v1 SDK, copied verbatim.


SPDX-License-Identifier: MIT
