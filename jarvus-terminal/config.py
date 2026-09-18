#!/usr/bin/env python3
"""Jarvus Terminal configuration. Every value here is safe to edit."""

from __future__ import annotations
import os

# --- what to scan -----------------------------------------------------------
# The universe pass is cheap (one request per venue). Deep analysis is expensive
# (one candle request per market), so only the top DEEP_SCAN_N by the cheap
# volatility pre-rank get analysed in full.
UNIVERSE_VENUES = ["okx_spot", "okx_swap", "coinbase"]
DEEP_SCAN_N = int(os.environ.get("JARVUS_DEEP_N", "40"))
MIN_USD_VOLUME_24H = float(os.environ.get("JARVUS_MIN_VOL", "3000000"))  # liquidity floor
QUOTE_WHITELIST = {"USDT", "USD", "USDC"}

# Markets always analysed regardless of rank.
ALWAYS_INCLUDE = ["BTC-USDT", "ETH-USDT", "SOL-USDT"]

# --- analysis ---------------------------------------------------------------
BIAS_TF = "4h"       # higher timeframe: trend/bias
SETUP_TF = "1h"      # setup timeframe: structure and the volatility gate
CANDLES = 300

# --- cost model (one side, basis points) ------------------------------------
# Cost in R = round-trip cost % / stop distance %. This gates every signal.
FEE_TIERS = {"Coinbase Advanced maker": 0.0, "MEXC maker": 0.0, "Binance spot": 10.0,
             "OKX spot": 10.0, "Kraken Pro maker": 16.0, "NDAX": 20.0, "Kraken Pro taker": 26.0}
DEFAULT_FEE_TIER = os.environ.get("JARVUS_FEE_TIER", "Kraken Pro taker")
SLIPPAGE_BPS = 2.0
MAX_COST_R = 0.33          # hard gate: above this, no trade
STOP_ATR_MULT = 4.0        # v5 finding: wide stops are what survive retail fees
TARGET_R = 2.0

# --- risk -------------------------------------------------------------------
DEFAULT_ACCOUNT = float(os.environ.get("JARVUS_ACCOUNT", "10000"))
RISK_PCT_A = 1.0
RISK_PCT_B = 0.5

# --- news -------------------------------------------------------------------
NEWS_FEEDS = [
    ("Cointelegraph", "https://cointelegraph.com/rss"),
    ("The Block", "https://www.theblock.co/rss.xml"),
    ("Decrypt", "https://decrypt.co/feed"),
    ("Bitcoin Magazine", "https://bitcoinmagazine.com/feed"),
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml"),
]
NEWS_MAX_ITEMS = 60

# --- caching / networking ---------------------------------------------------
CACHE_TTL_UNIVERSE = 120     # seconds
CACHE_TTL_CANDLES = 180
CACHE_TTL_NEWS = 600
HTTP_TIMEOUT = 20
MAX_WORKERS = 8              # concurrent candle fetches; be polite to public APIs

# --- storage ----------------------------------------------------------------
DB_PATH = os.environ.get("JARVUS_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "jarvus.db"))

# --- server -----------------------------------------------------------------
HOST = os.environ.get("JARVUS_HOST", "127.0.0.1")
PORT = int(os.environ.get("JARVUS_PORT", "8787"))

# --- learning ---------------------------------------------------------------
# Horizons (hours) at which a prediction is scored against what actually happened.
RESOLVE_HORIZON_H = 12
MIN_SAMPLES_FOR_CALIBRATION = 20
