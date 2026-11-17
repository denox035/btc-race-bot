"""Dip-swing BTC bot for make.fun's "Race a BTC trading bot live for 24 hours".

Strategy (long-only, one symbol, one position at a time):

* Wait for 240 one-minute bars of history (4h of context) before the first trade.
* BUY the whole cash balance when the close is at least 0.8% below the rolling
  120-bar high AND the 12-bar EMA has turned up over the last 15 bars
  (a multi-hour dip that is starting to recover, not a falling knife).
* SELL on the first of: take-profit +1.8% vs the buy's notional, stop-loss
  -1.0% vs the buy's notional, or a trailing stop 0.8% below the peak value
  of the position (only while the position is in profit).
* After any sell, sit out 30 bars before the next buy.

Dev-window result (kit grade-local, all fees/slippage/impact in):
net PnL +$21.22, 5 orders, max drawdown 1.57% -- vs the momentum baseline's
+$2.45 and buy-and-hold's +$1.07 on the same window.

Protocol: agent-fun/bars-replay/v1. The harness sends one hello line, then one
batch per minute; the bot answers every batch with exactly one reply echoing
its seq, carrying its orders for that bar. Orders decided on a bar fill at the
next bar's open. The vendored shim (vendor/makefun_bars.py) owns the wire.

Python 3.13 standard library only. Deterministic: no clock, no environment,
no randomness, no network, no files. The same bars always produce the same
orders.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

# --- strategy parameters (tuned only on the kit's shipped dev window) ---
HISTORY_BARS = 240        # bars of history before the first trade
HIGH_WINDOW = 120         # rolling-high window for the dip reference (bars)
EMA_SPAN = 12             # fast EMA span (bars)
EMA_RISE_BARS = 15        # EMA must be higher than this many bars ago
DIP_BPS = 80              # buy when close is >= 0.8% below the rolling high
TAKE_PROFIT_BPS = 180     # sell at +1.8% vs the buy's notional
STOP_LOSS_BPS = 100       # sell at -1.0% vs the buy's notional
TRAILING_BPS = 80         # sell 0.8% below the position's peak value (in profit)
COOLDOWN_BARS = 30        # bars to sit out after a sell
MAX_SLIPPAGE_BPS = 100    # bound on the move from the latest close


class DipSwingBot:
    """Keeps the indicator state across batches and decides the orders."""

    def __init__(self, symbol, price_scale):
        self.symbol = symbol
        self.price_scale = price_scale
        self.closes = []          # close prices in USD, one per bar
        self.ema = None           # 12-bar EMA of the close
        self.ema_hist = []        # EMA value after each bar
        self.entry_cost = None    # quote units the current position cost
        self.peak_val = 0         # peak quote value of the current position
        self.cool_until = -1      # first seq on which a new buy is allowed

    def _price(self, close_int):
        return close_int / (10 ** self.price_scale)

    def _note_bar(self, close):
        """Fold one new bar's close into the indicators."""
        self.closes.append(close)
        if len(self.closes) == EMA_SPAN:
            self.ema = sum(self.closes) / EMA_SPAN
        elif len(self.closes) > EMA_SPAN:
            k = 2.0 / (EMA_SPAN + 1)
            self.ema = self.ema + k * (close - self.ema)
        if self.ema is not None:
            self.ema_hist.append(self.ema)

    def _rolling_high(self):
        return max(self.closes[-HIGH_WINDOW:])

    def on_batch(self, state, batch):
        symbol = self.symbol
        # Fold in this batch's bar (if any) before deciding.
        has_bar = any(b.get("symbol") == symbol for b in batch.get("bars", []))
        if has_bar:
            close = state.close(symbol)
            if close is not None:
                self._note_bar(self._price(close))

        # Sync the position bookkeeping with the account the batch carries.
        held = state.positions.get(symbol)
        if held is None:
            self.entry_cost = None
            self.peak_val = 0
        else:
            if self.entry_cost is None:
                self.entry_cost = held.cost
            val = state.value(symbol, held.qty)
            if val > self.peak_val:
                self.peak_val = val

        # Warm-up batches build history only; every order on one is rejected.
        if state.warming_up:
            return []

        # First decision at bar index HISTORY_BARS (241 closes seen), exactly
        # as in the offline sweep that validated the parameters.
        if len(self.closes) <= HISTORY_BARS or self.ema is None:
            return []

        close = state.close(symbol)
        if close is None:
            return []

        if held is None:
            # Flat: look for a recovering multi-hour dip.
            if state.seq < self.cool_until:
                return []
            if len(self.ema_hist) <= EMA_RISE_BARS:
                return []
            price = self._price(close)
            dip = price / self._rolling_high() - 1.0
            rising = self.ema_hist[-1] > self.ema_hist[-1 - EMA_RISE_BARS]
            if dip * 10000 <= -DIP_BPS and rising:
                room = state.weight_room(symbol)
                notional = min(state.cash, room)
                min_notional = int(state.hello.get("fees", {}).get(
                    "min_notional_quote_units", 1_000_000
                ))
                if notional < min_notional:
                    return []
                self.entry_cost = notional
                self.peak_val = 0
                return [{
                    "side": "buy",
                    "symbol": symbol,
                    "notional_quote_units": int(notional),
                    "max_slippage_bps": MAX_SLIPPAGE_BPS,
                }]
            return []

        # Long: take-profit, stop-loss, or trailing stop.
        val = state.value(symbol, held.qty)
        cost = self.entry_cost if self.entry_cost else held.cost
        sell = False
        if val >= cost * (10000 + TAKE_PROFIT_BPS) // 10000:
            sell = True
        elif val <= cost * (10000 - STOP_LOSS_BPS) // 10000:
            sell = True
        elif val > cost and val <= self.peak_val * (10000 - TRAILING_BPS) // 10000:
            sell = True
        if sell:
            self.cool_until = state.seq + COOLDOWN_BARS
            self.entry_cost = None
            self.peak_val = 0
            return [{
                "side": "sell",
                "symbol": symbol,
                "qty": int(held.qty),
                "max_slippage_bps": MAX_SLIPPAGE_BPS,
            }]
        return []


def on_hello(state):
    symbols = state.hello.get("symbols", [])
    symbol = symbols[0]["symbol"] if symbols else "CBBTC"
    price_scale = symbols[0].get("price_scale", 5) if symbols else 5
    state.bot = DipSwingBot(symbol, price_scale)


def on_batch(state, batch):
    return state.bot.on_batch(state, batch)


makefun_bars.run(on_batch, on_hello=on_hello)
