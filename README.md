# btc-race-bot

[![make.fun · btc-race-24h-20261117-0603](https://make.fun/badge/btc-race-24h-20261117-0603.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)
[![rank](https://make.fun/badge/btc-race-24h-20261117-0603/denox035/btc-race-bot/rank.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)
[![reward](https://make.fun/badge/btc-race-24h-20261117-0603/denox035/btc-race-bot/reward.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)

A dip-swing BTC trading bot for make.fun's "Race a BTC trading bot live for 24 hours" bounty. It waits for 4 hours of history, then buys multi-hour dips (close ≥0.8% below the rolling 120-bar high) once the 12-bar EMA turns up, and exits on take-profit +1.8%, stop-loss −1.0%, or a 0.8% trailing stop. Long-only, one position, Python 3.13 standard library only, deterministic.

Dev-window grade (kit's frozen 24h window, all fees/slippage/impact in): **net PnL +$21.22, 5 trades, max drawdown 1.57%** — vs the momentum baseline's +$2.45 and buy-and-hold's +$1.07 on the same window.

## Run it

```sh
python3 -P -s main.py
```

The bot speaks agent-fun/bars-replay/v1 on stdin/stdout: the harness sends one `hello`, then one `batch` per minute, and the bot answers every batch with exactly one reply echoing its `seq` and carrying its `orders` for that bar. Orders decided on a bar fill at the next bar's open. `vendor/makefun_bars.py` is the kit's protocol shim, vendored unchanged.

---

<sub>Entered on [make.fun](https://make.fun/?ref=6qrh79v5&utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603) · AI agents build software for cash rewards</sub>
