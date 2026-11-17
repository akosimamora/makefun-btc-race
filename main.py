"""Deep-dip mean-reversion bot for make.fun btc-race-24h-20261117-0603.

Strategy (long only, one position, full size):
  - Buy after a deep pullback: the close falls at least DIP_BPS below the
    highest close of the last HIGH_W bars. Shallow dips are noise in this
    market (they lose money after fees); a >=1.2% pullback marks a real
    swing low, and the bounce after it is usually larger than the
    ~15 bps round-trip cost.
  - Sell at take-profit TP_BPS above cost, or stop-loss SL_BPS below cost,
    or after TIMEOUT_BARS bars without either (free the capital for the
    next dip). Cost is the cash spent, fees included.
  - A 10-bar cooldown after every exit keeps the bot from re-buying the
    same falling leg at once.
  - A drawdown brake halts new entries if equity falls 3% below its peak
    (it resumes at 0.5% below peak): on a race window that trends down
    all day this caps the bleeding instead of buying every dip down.
  - Fallback: if the bot still has no fill by bar FALLBACK_BAR and the
    close sits above its 240-bar average (a mild uptrend), it buys once
    at market, so a calm window still leaves it with a trade and some
    drift exposure instead of a flat zero.

Everything is deterministic: fixed parameters, float64 closes only, no
clock, no environment, no randomness. Two runs produce byte-identical
action logs.
"""

import os
import sys
from collections import deque

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"

# --- strategy parameters (calibrated on the dev window; see the sweep) ---
HIGH_W = 60            # rolling-high window (bars)
DIP_BPS = 120          # buy when close <= high * (1 - 120 bps)
TP_BPS = 150           # take profit: position value >= cost * (1 + 150 bps)
SL_BPS = 80            # stop loss: position value <= cost * (1 - 80 bps)
TIMEOUT_BARS = 360     # sell if neither TP nor SL after this many bars
COOLDOWN_BARS = 10     # bars to wait after an exit before a new entry
MAX_SLIPPAGE_BPS = 100  # 1% past the close the order was decided on
BRAKE_BPS = 300        # halt new entries at 3% below peak equity
RESUME_BPS = 50        # resume entries at 0.5% below peak equity
FALLBACK_BAR = 1080    # no fill by here -> one trend-gated market buy
SMA_W = 240            # average for the fallback's trend check


class Bot:
    def __init__(self):
        self.closes = []              # float closes in USD, oldest first
        self.high = deque()           # (seq, close) of the rolling HIGH_W max
        self.sma_sum = 0.0            # running sum of the last SMA_W closes
        self.sma_q = deque()          # closes feeding the SMA
        self.entry_seq = -1           # seq of the bar the open position was decided on
        self.cool_until = -1          # no new entry before this seq
        self.peak_equity = None       # highest equity seen (quote units)
        self.halted = False           # drawdown brake latched
        self.fills = 0                # filled buy orders so far
        self.fallback_done = False    # the fallback buy already fired
        self.price_scale = 5          # CBBTC: 10^5 raw units per USDC

    def on_hello(self, state):
        for s in state.hello["symbols"]:
            if s["symbol"] == SYMBOL:
                self.price_scale = int(s["price_scale"])

    def push_bar(self, bar):
        close = int(bar["c"]) / (10 ** self.price_scale)
        seq = len(self.closes)
        self.closes.append(close)
        # rolling max over the last HIGH_W closes, current bar included
        while self.high and self.high[0][0] <= seq - HIGH_W:
            self.high.popleft()
        while self.high and self.high[-1][1] <= close:
            self.high.pop()
        self.high.append((seq, close))
        # 240-bar simple moving average
        self.sma_q.append(close)
        self.sma_sum += close
        if len(self.sma_q) > SMA_W:
            self.sma_sum -= self.sma_q.popleft()
        return close

    def rolling_high(self):
        return self.high[0][1] if self.high else None

    def sma(self):
        if len(self.sma_q) < SMA_W:
            return None
        return self.sma_sum / SMA_W

    def on_batch(self, state, batch):
        for fill in batch.get("fills", []):
            if fill.get("status") == "filled" and fill.get("side") == "buy":
                self.fills += 1
        for bar in batch.get("bars", []):
            if bar.get("symbol") == SYMBOL:
                self.push_bar(bar)
        if state.warming_up:
            return []
        if not self.closes:
            return []

        seq = state.seq
        close = self.closes[-1]

        # drawdown brake on peak equity (exact integer math, in bps):
        # halt new entries once equity is BRAKE_BPS below its peak, and
        # resume them once it has recovered to RESUME_BPS below the peak.
        if self.peak_equity is None:
            self.peak_equity = state.equity
        elif state.equity > self.peak_equity:
            self.peak_equity = state.equity
        if state.equity * 10000 < self.peak_equity * (10000 - BRAKE_BPS):
            self.halted = True
        if self.halted and state.equity * 10000 >= self.peak_equity * (10000 - RESUME_BPS):
            self.halted = False

        held = state.positions.get(SYMBOL)
        if held is not None:
            # exit: take-profit, stop-loss, or timeout
            val = state.value(SYMBOL, held.qty)
            cost = held.cost
            ret_bps = (val - cost) * 10000 // cost if cost > 0 else 0
            if ret_bps >= TP_BPS or ret_bps <= -SL_BPS or (seq - self.entry_seq) >= TIMEOUT_BARS:
                self.cool_until = seq + COOLDOWN_BARS
                return [{"side": "sell", "symbol": SYMBOL, "qty": held.qty,
                         "max_slippage_bps": MAX_SLIPPAGE_BPS}]
            return []

        # flat: no new entry while halted, cooling down, or too early
        if self.halted or seq < self.cool_until or len(self.closes) < HIGH_W:
            return []

        high = self.rolling_high()
        if high is not None and close * 10000 <= high * (10000 - DIP_BPS):
            self.entry_seq = seq
            return [{"side": "buy", "symbol": SYMBOL,
                     "notional_quote_units": state.cash,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]

        # fallback: no fill yet late in the window, mild uptrend -> buy once
        if (not self.fallback_done and self.fills == 0 and seq >= FALLBACK_BAR):
            avg = self.sma()
            if avg is not None and close > avg and state.cash >= 2 * 1000000:
                self.fallback_done = True
                self.entry_seq = seq
                return [{"side": "buy", "symbol": SYMBOL,
                         "notional_quote_units": state.cash,
                         "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        return []


BOT = Bot()


def on_batch(state, batch):
    return BOT.on_batch(state, batch)


def on_hello(state):
    BOT.on_hello(state)


makefun_bars.run(on_batch, on_hello=on_hello)
