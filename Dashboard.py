import time
from datetime import datetime, timezone

import ccxt
import numpy as np
import pandas as pd
import requests
import streamlit as st

# Import the backtesting library
from backtesting import Backtest, Strategy

# --------------------------------------------------------------------------- #
# Custom Native Pandas Indicators (Replaces pandas_ta)
# --------------------------------------------------------------------------- #
def calculate_sma(series: pd.Series, length: int) -> pd.Series:
    """Simple Moving Average"""
    return series.rolling(window=length).mean()

def calculate_ema(series: pd.Series, length: int) -> pd.Series:
    """Exponential Moving Average"""
    return series.ewm(span=length, adjust=False).mean()

def calculate_rsi(series: pd.Series, length: int) -> pd.Series:
    """Relative Strength Index (Wilder's Standard Smoothing)"""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    
    # Wilder's smoothing method uses alpha = 1 / length
    avg_gain = gain.ewm(alpha=1/length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/length, adjust=False).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    # If loss is 0, RS is infinite and RSI is 100
    rsi = rsi.replace([np.inf, -np.inf], 100)
    return rsi

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
TIMEFRAME = "1d"
CANDLE_LIMIT = 500
TOP_N = 50
RSI_PERIOD = 14
DEFAULT_RSI_LEVEL = 30
VOL_SMA_PERIOD = 20
DEFAULT_VOL_MULTIPLIER = 1.5
EMA_PERIOD = 200
MAX_RETRIES = 3

EXCLUDE = {
    "USDT", "USDC", "FDUSD", "TUSD", "DAI", "USDE", "USDS", "USDD", "PYUSD",
    "BUSD", "USDP", "USD1", "WBTC", "WBETH", "STETH", "WSTETH", "WEETH", "BSC-USD",
    "BNSOL", "CBBTC", "LEO", "BGB",
}

FALLBACK_SYMBOLS = [
    "BTC", "ETH", "XRP", "BNB", "SOL", "DOGE", "TRX", "ADA", "LINK", "AVAX",
    "XLM", "SUI", "BCH", "HBAR", "LTC", "TON", "SHIB", "DOT", "UNI", "AAVE",
]

# --------------------------------------------------------------------------- #
# Backtesting Strategy Class
# --------------------------------------------------------------------------- #
def get_rsi(array, length):
    return calculate_rsi(pd.Series(array), length).values

def get_ema(array, length):
    return calculate_ema(pd.Series(array), length).values

def get_sma(array, length):
    return calculate_sma(pd.Series(array), length).values

class RsiEmaPullback(Strategy):
    rsi_level = 30
    vol_mult = 1.5
    
    def init(self):
        self.rsi = self.I(get_rsi, self.data.Close, RSI_PERIOD)
        self.ema200 = self.I(get_ema, self.data.Close, EMA_PERIOD)
        self.vol_sma = self.I(get_sma, self.data.Volume, VOL_SMA_PERIOD)
        
    def next(self):
        if len(self.data) < EMA_PERIOD:
            return
            
        current_price = self.data.Close[-1]
        current_rsi = self.rsi[-1]
        current_vol = self.data.Volume[-1]
        current_vol_sma = self.vol_sma[-1]
        current_ema = self.ema200[-1]
        
        # BUY LOGIC
        if (current_rsi <= self.rsi_level and 
            current_price > current_ema and 
            current_vol > (current_vol_sma * self.vol_mult)):
            
            if not self.position:
                self.buy()
                
        # SELL LOGIC 
        elif current_rsi >= 50:
            if self.position:
                self.position.close()

# --------------------------------------------------------------------------- #
# Data layer
# --------------------------------------------------------------------------- #
@st.cache_resource
def get_exchange() -> ccxt.binance:
    exchange = ccxt.binance({"enableRateLimit": True})
    exchange.load_markets()
    return exchange

def _with_retries(fn, *args, **kwargs):
    for attempt in range(MAX_RETRIES):
        try:
            return fn(*args, **kwargs)
        except (ccxt.NetworkError, ccxt.RateLimitExceeded, ccxt.RequestTimeout):
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep(1.5 * (2 ** attempt))

@st.cache_data(ttl=3600, show_spinner=False)
def get_top_symbols_by_market_cap(n: int = TOP_N) -> tuple[list[str], str]:
    exchange = get_exchange()
    tradable = {
        m.get("base") for m in (exchange.markets or {}).values()
        if m.get("quote") == "USDT" and m.get("spot") and m.get("active") and m.get("base")
    }

    try:
        resp = requests.get(
            "https://api.coingecko.com/api/v3/coins/markets",
            params={"vs_currency": "usd", "order": "market_cap_desc", "per_page": 150, "page": 1},
            timeout=15,
        )
        resp.raise_for_status()
        ranked = [c["symbol"].upper() for c in resp.json()]
        source = "CoinGecko"
    except Exception:
        ranked = FALLBACK_SYMBOLS
        source = "Static fallback list"

    symbols: list[str] = []
    for sym in ranked:
        if sym in EXCLUDE or sym not in tradable or f"{sym}/USDT" in symbols:
            continue
        symbols.append(f"{sym}/USDT")
        if len(symbols) == n:
            break
    return symbols, source

@st.cache_data(ttl=300, show_spinner=False)
def fetch_candles(symbol: str) -> pd.DataFrame | None:
    try:
        ohlcv = _with_retries(get_exchange().fetch_ohlcv, symbol, timeframe=TIMEFRAME, limit=CANDLE_LIMIT)
    except Exception:
        return None
    df = pd.DataFrame(ohlcv, columns=["ts", "open", "high", "low", "close", "volume"])
    df["date"] = pd.to_datetime(df["ts"], unit="ms")
    return df

@st.cache_data(ttl=60, show_spinner=False)
def fetch_all_tickers(symbols: tuple[str, ...]) -> dict:
    try:
        # Calling fetch_tickers() with no arguments fetches the entire market safely.
        # This prevents the script from crashing if 1 specific symbol is halted/invalid.
        all_tickers = _with_retries(get_exchange().fetch_tickers)
        
        # Filter down to only the symbols we care about
        return {
            sym: ticker
            for sym in symbols
            if (ticker := (all_tickers or {}).get(sym)) is not None
        }
    except Exception as e:
        print(f"Warning: Could not fetch live tickers: {e}")
        return {}

# --------------------------------------------------------------------------- #
# Signal logic
# --------------------------------------------------------------------------- #
def analyze_symbol(symbol: str, candles: pd.DataFrame | None, ticker: dict, require_fresh_cross: bool, rsi_level: float, vol_multiplier: float) -> dict:
    row = {
        "Ticker": symbol.replace("/USDT", ""),
        "Price": np.nan, "RSI": np.nan, "Volume Surge %": np.nan,
        "Signal Status": "FETCH ERROR", "Conditions Met": 0,
    }

    if candles is None or len(candles) < EMA_PERIOD + 1:
        row["Signal Status"] = "INSUFFICIENT HISTORY"
        return row

    df = candles.copy()
    price = ticker.get("last") or df["close"].iloc[-1]
    df.loc[df.index[-1], "close"] = price

    # Native Calculations
    rsi = calculate_rsi(df["close"], RSI_PERIOD)
    ema200 = calculate_ema(df["close"], EMA_PERIOD)
    vol_sma20 = calculate_sma(df["volume"].iloc[:-1], VOL_SMA_PERIOD)

    rsi_now, rsi_prev = rsi.iloc[-1], rsi.iloc[-2]
    ema_now = ema200.iloc[-1]
    vol_sma_now = vol_sma20.iloc[-1]
    vol_24h = ticker.get("baseVolume") or df["volume"].iloc[-1]

    if pd.isna(rsi_now) or pd.isna(ema_now) or pd.isna(vol_sma_now) or vol_sma_now == 0:
        row["Signal Status"] = "INSUFFICIENT HISTORY"
        return row

    vol_ratio_pct = (vol_24h / vol_sma_now) * 100

    cond_rsi = rsi_now <= rsi_level
    if require_fresh_cross:
        cond_rsi = cond_rsi and (rsi_prev > rsi_level or rsi_now == rsi_level)
    cond_vol = vol_24h > vol_multiplier * vol_sma_now
    cond_trend = price > ema_now
    is_buy = bool(cond_rsi and cond_vol and cond_trend)

    row.update({
        "Price": price, "RSI": rsi_now, "Volume Surge %": vol_ratio_pct,
        "Signal Status": "BUY" if is_buy else "NO SIGNAL",
        "Conditions Met": int(cond_rsi) + int(cond_vol) + int(cond_trend),
    })
    return row

def highlight_rows(row: pd.Series, show_near_miss: bool) -> list[str]:
    if row["Signal Status"] == "BUY":
        return ["background-color: #1b8a3b; color: white; font-weight: 600"] * len(row)
    if show_near_miss and row.get("Conditions Met") == 2:
        return ["background-color: #fff3cd; color: #5c4400"] * len(row)
    return [""] * len(row)

# --------------------------------------------------------------------------- #
# Presentation
# --------------------------------------------------------------------------- #
def main() -> None:
    st.set_page_config(page_title="Crypto Signal Dashboard", page_icon="📈", layout="wide")
    st.title("📈 Crypto Signal Dashboard (Native Math)")

    with st.sidebar:
        st.header("Settings")
        fresh_cross = st.checkbox("Require fresh RSI cross", value=False)
        only_buys = st.checkbox("Show BUY signals only", value=False)
        show_near_miss = st.checkbox("Highlight near misses", value=True)

        with st.expander("Advanced rule parameters"):
            rsi_level = st.slider("RSI level", 10, 50, DEFAULT_RSI_LEVEL)
            vol_mult_pct = st.slider("Volume threshold (% of 20d avg)", 100, 400, int(DEFAULT_VOL_MULTIPLIER * 100), step=10)
            vol_multiplier = vol_mult_pct / 100

        if st.button("🔄 Refresh data"):
            st.cache_data.clear()
            st.rerun()

    try:
        symbols, source = get_top_symbols_by_market_cap()
    except Exception as exc:
        st.error(f"Could not reach Binance: {exc}")
        st.stop()

    tickers = fetch_all_tickers(tuple(symbols))
    candle_map: dict[str, pd.DataFrame | None] = {}
    progress = st.progress(0.0, text="Scanning markets...")
    for i, symbol in enumerate(symbols, start=1):
        candle_map[symbol] = fetch_candles(symbol)
        progress.progress(i / len(symbols))
    progress.empty()

    rows = [analyze_symbol(s, candle_map[s], tickers.get(s, {}), fresh_cross, rsi_level, vol_multiplier) for s in symbols]
    df = pd.DataFrame(rows)

    view = df.copy()
    if only_buys:
        view = view[view["Signal Status"] == "BUY"]

    view["_buy"] = (view["Signal Status"] == "BUY").astype(int)
    view = view.sort_values(["_buy", "Conditions Met", "RSI"], ascending=[False, False, True]).drop(columns="_buy")

    core_cols = ["Ticker", "Price", "RSI", "Volume Surge %", "Conditions Met", "Signal Status"]
    view = view[core_cols].reset_index(drop=True)

    if not view.empty:
        fmt = {"Price": "${:,.4f}", "RSI": "{:.1f}", "Volume Surge %": "{:,.0f}%"}
        styled = (
            view.style.apply(highlight_rows, axis=1, show_near_miss=show_near_miss)
            .format("${:,.4f}", subset=["Price"], na_rep="-")
            .format("{:.1f}", subset=["RSI"], na_rep="-")
            .format("{:,.0f}%", subset=["Volume Surge %"], na_rep="-")
        )
        st.dataframe(styled, use_container_width=True, height=min(600, 40 + 35 * len(view)), hide_index=True)

    # ---- Per-coin chart and Backtest --------------------------------------
    st.divider()
    st.subheader("Asset Deep Dive & Backtest")
    
    tickers_list = [t for t in view["Ticker"].tolist()]
    pick = st.selectbox("Select asset to chart and backtest", tickers_list)
    candles = candle_map.get(f"{pick}/USDT")
    
    if candles is not None and len(candles) > EMA_PERIOD:
        chart_df = candles.set_index("date")[["close"]].rename(columns={"close": "Close"})
        chart_df["EMA200"] = calculate_ema(candles["close"], EMA_PERIOD).values
        st.line_chart(chart_df.tail(180))
        
        st.write(f"### Historical Backtest Results ({pick})")
        st.caption(f"Testing RSI <= {rsi_level}, Volume > {vol_mult_pct}%, Price > EMA200.")
        
        bt_df = candles.copy().rename(columns={'date': 'Date', 'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}).set_index('Date')
        
        bt = Backtest(bt_df, RsiEmaPullback, cash=10000, commission=0.001, exclusive_orders=True)
        stats = bt.run(rsi_level=rsi_level, vol_mult=vol_multiplier)
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Return [%]", f"{stats['Return [%]']:.2f}%")
        col2.metric("Win Rate [%]", f"{stats['Win Rate [%]']:.2f}%" if not pd.isna(stats['Win Rate [%]']) else "0.00%")
        col3.metric("Total Trades", str(stats['# Trades']))
        col4.metric("Max Drawdown [%]", f"{stats['Max. Drawdown [%]']:.2f}%")
        
        with st.expander("Show Full Backtest Logs"):
            st.code(stats.to_string())
    else:
        st.info("Not enough data to chart or backtest this asset.")

if __name__ == "__main__":
    main()