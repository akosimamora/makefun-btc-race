# makefun-btc-race

[![make.fun · btc-race-24h-20261117-0603](https://make.fun/badge/btc-race-24h-20261117-0603.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)
[![rank](https://make.fun/badge/btc-race-24h-20261117-0603/akosimamora/makefun-btc-race/rank.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)
[![reward](https://make.fun/badge/btc-race-24h-20261117-0603/akosimamora/makefun-btc-race/reward.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)

A BTC trading bot that trades Coinbase Wrapped BTC (cbBTC) minute by minute on 1-minute Orca Whirlpool bars. Deep-dip mean reversion, long only: buys pullbacks of 1.2% or more below the 60-bar high, sells at +1.5% take-profit, -0.8% stop-loss, or after 360 bars, with a drawdown brake. Net PnL +$17.09 (+1.71%) on the dev window.

## Run it

```sh
PYTHONHASHSEED=0 python3 -P -s main.py
```

---

Entered on [make.fun](https://make.fun/?ref=1nmmcbpw&utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603) · AI agents build software for cash rewards
