"""The instrument universe: US stocks and crypto (traded), plus ETFs and indices kept only as price references.

Nothing here is a broker connection. A data source is named for every instrument; when the only data is a provider's
continuous futures series or a reference FX mid (no dealer bid/ask), that limitation is carried as a tag and shown.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from tradingai.market.instruments import Instrument, InstrumentBook, MarketType, Settlement
from tradingai.market.policy import market_allowed

D = Decimal


@dataclass(frozen=True)
class DataSource:
    provider: str            # coinbase | kraken | yahoo | demo
    symbol: str              # the provider's own symbol
    note: str = ""


CRYPTO = [("COINBASE", "BTC-USD", "coinbase", "BTC-USD"), ("COINBASE", "ETH-USD", "coinbase", "ETH-USD"),
          ("COINBASE", "SOL-USD", "coinbase", "SOL-USD"), ("KRAKEN", "XBTUSD", "kraken", "XBTUSD"),
          ("KRAKEN", "ETHUSD", "kraken", "ETHUSD")]
STOCKS = ["AAPL", "MSFT", "NVDA", "AMZN", "TSLA", "JPM", "XOM"]
ETFS = ["SPY", "QQQ", "IWM", "DIA", "TLT", "GLD", "XLE",
        # added for the catalog's portfolio templates (ST001-E, ST004, ST005, ST010, ST017): sector SPDRs, international
        # equity, bonds, commodities and REITs, all liquid US-listed ETFs with long daily histories
        "XLK", "XLF", "XLV", "XLY", "XLP", "XLI", "XLB", "XLU", "EFA", "EEM", "IEF", "SHY", "DBC", "VNQ"]
# 1.4.0: more liquid US large caps and ETFs so each equities agent (A001-A096) watches a distinct real market. All were
# checked to return Yahoo chart data on 2026-10-11. They are not part of any catalog portfolio universe.
STOCKS_MORE = ["GOOGL", "META", "AVGO", "BRK-B", "LLY", "V", "MA", "UNH", "COST", "WMT", "HD", "PG", "JNJ", "ORCL",
               "NFLX", "ABBV", "BAC", "KO", "PEP", "CRM", "AMD", "CVX", "MRK", "ADBE", "TMO", "CSCO", "ACN", "MCD", "ABT",
               "WFC", "INTC", "QCOM", "TXN", "IBM", "GS", "MS", "CAT", "DIS", "VZ", "T", "PFE", "NKE", "UBER", "PYPL",
               "BA", "GE", "HON", "AMGN", "SBUX", "LOW", "PLTR", "COIN"]
ETFS_MORE = ["VOO", "VTI", "IVV", "SMH", "XBI", "ARKK", "HYG", "LQD", "SLV", "USO", "GDX", "KRE", "XLC", "XLRE",
             "IBIT", "VEA"]
INDICES = {"SPX": "^GSPC", "NDX": "^NDX", "DJI": "^DJI", "RUT": "^RUT"}
DEMO = ["DEMO-TREND", "DEMO-RANGE", "DEMO-VOLATILE"]


def build() -> tuple[InstrumentBook, dict[str, DataSource]]:
    book = InstrumentBook()
    src: dict[str, DataSource] = {}
    for venue, sym, prov, psym in CRYPTO:
        base, quote = (sym.split("-") if "-" in sym else (sym[:-3].replace("XBT", "BTC"), sym[-3:]))
        i = book.add(Instrument(f"{venue}:{sym}", MarketType.CRYPTO_SPOT, sym, venue, quote, tick_size=D("0.01"),
                                quantity_step=D("0.00000001"), min_quantity=D("0.00000001"), base_asset=base,
                                quote_asset=quote, calendar="CRYPTO", data_source=prov, exchange=venue))
        src[i.instrument_id] = DataSource(prov, psym, "public exchange candles")
    for s in STOCKS + ETFS + STOCKS_MORE + ETFS_MORE:
        etf = s in ETFS or s in ETFS_MORE
        i = book.add(Instrument(f"US:{s}", MarketType.ETF if etf else MarketType.STOCK, s, "US", "USD",
                                tick_size=D("0.01"), quantity_step=D(1), min_quantity=D(1), calendar="XNYS",
                                data_source="yahoo", tags=("reference_only",) if etf else ()))
        src[i.instrument_id] = DataSource("yahoo", s, "Yahoo Finance chart data (unofficial; split/dividend adjusted)")
    for name, ysym in INDICES.items():
        i = book.add(Instrument(f"INDEX:{name}", MarketType.INDEX_REFERENCE, name, "INDEX", "USD",
                                settlement=Settlement.NONE, calendar="XNYS", data_source="yahoo"))
        src[i.instrument_id] = DataSource("yahoo", ysym, "calculated index: a reference, never ordered")
    for d in DEMO:
        i = book.add(Instrument(f"DEMO:{d}", MarketType.CRYPTO_SPOT, d, "DEMO", "USD", tick_size=D("0.01"),
                                quantity_step=D("0.0001"), min_quantity=D("0.0001"), calendar="CRYPTO",
                                data_source="demo", tags=("simulated",)))
        src[i.instrument_id] = DataSource("demo", d, "SIMULATED prices for offline use: not a real market")
    return book, src


def paper_tradable(inst: Instrument) -> tuple[bool, str]:
    """Whether the paper engine may trade this instrument, and why not."""
    return market_allowed(inst)
