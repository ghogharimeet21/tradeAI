# =========================================================================
# Tools — all pure functions, no state
#
# ⚠  REGISTRY RULE — read before adding anything here:
#
#   Before writing a new function, run:
#       python registry.py find "<your intent>"
#   or in Python:
#       import registry; registry.check_before_create("<your intent>")
#
#   If an equivalent tool already exists → REUSE it.
#   If not → create it here, then call registry.add_tool(...) to register it.
#
#   CONSTANTS: never redefine BINANCE_BASE — import it from constants.py.
# =========================================================================

import requests

from constants import BINANCE_BASE


def get_price(symbol: str) -> str:
    """Get current price for a symbol e.g. BTCUSDT"""
    symbol = symbol.upper()
    r = requests.get(f"{BINANCE_BASE}/ticker/price", params={"symbol": symbol})
    r.raise_for_status()
    data = r.json()
    return f"{symbol} price: {float(data['price']):.4f} USDT"


def get_ohlcv(args: str) -> str:
    """
    Get recent OHLCV candles.
    args format: "BTCUSDT,5m,10"  (symbol, interval, limit)
    """
    parts = [p.strip() for p in args.split(",")]
    symbol   = parts[0].upper()
    interval = parts[1] if len(parts) > 1 else "1m"
    limit    = int(parts[2]) if len(parts) > 2 else 5

    r = requests.get(f"{BINANCE_BASE}/klines", params={
        "symbol": symbol, "interval": interval, "limit": limit
    })
    r.raise_for_status()
    candles = r.json()

    lines = [f"{symbol} {interval} OHLCV (last {limit} candles):"]
    for c in candles:
        lines.append(f"  open={float(c[1]):.2f} high={float(c[2]):.2f} "
                     f"low={float(c[3]):.2f} close={float(c[4]):.2f} vol={float(c[5]):.2f}")
    return "\n".join(lines)


def get_orderbook(args: str) -> str:
    """
    Get top N order book levels.
    args format: "BTCUSDT,5"  (symbol, depth)
    """
    parts = [p.strip() for p in args.split(",")]
    symbol = parts[0].upper()
    depth  = int(parts[1]) if len(parts) > 1 else 5

    r = requests.get(f"{BINANCE_BASE}/depth", params={"symbol": symbol, "limit": depth})
    r.raise_for_status()
    data = r.json()

    bids = data["bids"][:depth]
    asks = data["asks"][:depth]

    lines = [f"{symbol} order book (top {depth}):"]
    lines.append("  ASKS (sell wall):")
    for price, qty in reversed(asks):
        lines.append(f"    {float(price):.2f}  x  {float(qty):.4f}")
    lines.append("  BIDS (buy wall):")
    for price, qty in bids:
        lines.append(f"    {float(price):.2f}  x  {float(qty):.4f}")
    return "\n".join(lines)


def get_24h_stats(symbol: str) -> str:
    """Get 24h rolling stats for a symbol"""
    symbol = symbol.upper()
    r = requests.get(f"{BINANCE_BASE}/ticker/24hr", params={"symbol": symbol})
    r.raise_for_status()
    d = r.json()
    return (
        f"{symbol} 24h stats:\n"
        f"  open={float(d['openPrice']):.4f}  close={float(d['lastPrice']):.4f}\n"
        f"  high={float(d['highPrice']):.4f}  low={float(d['lowPrice']):.4f}\n"
        f"  change={float(d['priceChangePercent']):.2f}%\n"
        f"  volume={float(d['volume']):.2f}  quoteVolume={float(d['quoteVolume']):.2f}"
    )


def calculate_sma(args: str) -> str:
    """
    Calculate SMA from recent closes.
    args format: "BTCUSDT,20,1m"  (symbol, period, interval)
    """
    parts  = [p.strip() for p in args.split(",")]
    symbol = parts[0].upper()
    period = int(parts[1]) if len(parts) > 1 else 20
    tf     = parts[2] if len(parts) > 2 else "1m"

    r = requests.get(f"{BINANCE_BASE}/klines", params={
        "symbol": symbol, "interval": tf, "limit": period
    })
    r.raise_for_status()
    closes = [float(c[4]) for c in r.json()]

    if len(closes) < period:
        return f"Not enough data for SMA({period})"

    sma = sum(closes[-period:]) / period
    current = closes[-1]
    position = "above" if current > sma else "below"
    return (f"{symbol} SMA({period}) on {tf}: {sma:.4f}\n"
            f"  current price {current:.4f} is {position} SMA")


def calculate_ema(args: str) -> str:
    """
    Calculate EMA from recent closes.
    args format: "BTCUSDT,9,21,1h"  (symbol, fast_period, slow_period, interval)
    Cross above = bullish, cross below = bearish.
    """
    parts  = [p.strip() for p in args.split(",")]
    symbol = parts[0].upper()
    fast   = int(parts[1]) if len(parts) > 1 else 9
    slow   = int(parts[2]) if len(parts) > 2 else 21
    tf     = parts[3] if len(parts) > 3 else "1h"

    limit = slow + 50
    r = requests.get(f"{BINANCE_BASE}/klines", params={
        "symbol": symbol, "interval": tf, "limit": limit
    })
    r.raise_for_status()
    closes = [float(c[4]) for c in r.json()]

    def ema(prices, period):
        k = 2 / (period + 1)
        e = prices[0]
        for p in prices[1:]:
            e = p * k + e * (1 - k)
        return e

    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    signal   = "BULLISH (fast above slow)" if ema_fast > ema_slow else "BEARISH (fast below slow)"

    return (f"{symbol} EMA on {tf}:\n"
            f"  EMA({fast}) = {ema_fast:.4f}\n"
            f"  EMA({slow}) = {ema_slow:.4f}\n"
            f"  Signal: {signal}")


def calculate_rsi(args: str) -> str:
    """
    Calculate RSI.
    args format: "BTCUSDT,14,1h"  (symbol, period, interval)
    """
    parts  = [p.strip() for p in args.split(",")]
    symbol = parts[0].upper()
    period = int(parts[1]) if len(parts) > 1 else 14
    tf     = parts[2] if len(parts) > 2 else "1h"

    r = requests.get(f"{BINANCE_BASE}/klines", params={
        "symbol": symbol, "interval": tf, "limit": period + 50
    })
    r.raise_for_status()
    closes = [float(c[4]) for c in r.json()]

    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains  = [max(d, 0) for d in deltas]
    losses = [abs(min(d, 0)) for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        rsi = 100.0
    else:
        rs  = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

    if rsi >= 70:
        zone = "OVERBOUGHT — possible reversal down"
    elif rsi <= 30:
        zone = "OVERSOLD — possible reversal up"
    else:
        zone = "NEUTRAL"

    return (f"{symbol} RSI({period}) on {tf}: {rsi:.2f}\n"
            f"  Zone: {zone}")


def detect_trend(args: str) -> str:
    """
    Simple trend detection via higher highs / lower lows over recent candles.
    args format: "BTCUSDT,20,1h"  (symbol, lookback, interval)
    """
    parts    = [p.strip() for p in args.split(",")]
    symbol   = parts[0].upper()
    lookback = int(parts[1]) if len(parts) > 1 else 20
    tf       = parts[2] if len(parts) > 2 else "1h"

    r = requests.get(f"{BINANCE_BASE}/klines", params={
        "symbol": symbol, "interval": tf, "limit": lookback
    })
    r.raise_for_status()
    candles = r.json()

    highs  = [float(c[2]) for c in candles]
    lows   = [float(c[3]) for c in candles]
    closes = [float(c[4]) for c in candles]

    first_half_high = max(highs[:lookback // 2])
    second_half_high = max(highs[lookback // 2:])
    first_half_low = min(lows[:lookback // 2])
    second_half_low = min(lows[lookback // 2:])

    higher_highs = second_half_high > first_half_high
    higher_lows  = second_half_low > first_half_low

    if higher_highs and higher_lows:
        trend = "UPTREND (higher highs + higher lows)"
    elif not higher_highs and not higher_lows:
        trend = "DOWNTREND (lower highs + lower lows)"
    else:
        trend = "SIDEWAYS / CONSOLIDATING"

    return (f"{symbol} trend over last {lookback} {tf} candles:\n"
            f"  {trend}\n"
            f"  recent close: {closes[-1]:.4f}")


def check_volume_spike(args: str) -> str:
    """
    Check if current volume is a spike vs rolling average.
    args format: "BTCUSDT,20,1h"  (symbol, lookback, interval)
    """
    parts    = [p.strip() for p in args.split(",")]
    symbol   = parts[0].upper()
    lookback = int(parts[1]) if len(parts) > 1 else 20
    tf       = parts[2] if len(parts) > 2 else "1h"

    r = requests.get(f"{BINANCE_BASE}/klines", params={
        "symbol": symbol, "interval": tf, "limit": lookback + 1
    })
    r.raise_for_status()
    candles = r.json()

    volumes     = [float(c[5]) for c in candles]
    current_vol = volumes[-1]
    avg_vol     = sum(volumes[:-1]) / lookback
    ratio       = current_vol / avg_vol if avg_vol > 0 else 0

    if ratio >= 2.0:
        verdict = f"SPIKE DETECTED ({ratio:.1f}x average)"
    elif ratio >= 1.5:
        verdict = f"ELEVATED volume ({ratio:.1f}x average)"
    else:
        verdict = f"Normal volume ({ratio:.1f}x average)"

    return (f"{symbol} volume on {tf}:\n"
            f"  current: {current_vol:.2f}\n"
            f"  {lookback}-bar avg: {avg_vol:.2f}\n"
            f"  {verdict}")


# =========================================================================
# Tool registry
# =========================================================================

TOOLS = {
    "get_price":          get_price,
    "get_ohlcv":          get_ohlcv,
    "get_orderbook":      get_orderbook,
    "get_24h_stats":      get_24h_stats,
    "calculate_sma":      calculate_sma,
    "calculate_ema":      calculate_ema,
    "calculate_rsi":      calculate_rsi,
    "detect_trend":       detect_trend,
    "check_volume_spike": check_volume_spike,
}