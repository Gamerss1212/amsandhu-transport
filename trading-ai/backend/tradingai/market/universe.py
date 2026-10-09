"""The default instrument universe across five markets, with where each one's data really comes from.

Nothing here is a broker connection. A data source is named for every instrument; when the only data is a provider's
continuous futures series or a reference FX mid (no dealer bid/ask), that limitation is carried as a tag and shown.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal

from tradingai.market.instruments import (INDEX_REFERENCES, Instrument, InstrumentBook, MarketType, Settlement,
                                          future_from_spec, load_specs)

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
FX = ["EURUSD", "GBPUSD", "USDJPY", "USDCAD", "AUDUSD"]
INDICES = {"SPX": "^GSPC", "NDX": "^NDX", "DJI": "^DJI", "RUT": "^RUT"}
FUTURES = {"ES": "ES=F", "MES": "MES=F", "NQ": "NQ=F", "MNQ": "MNQ=F", "YM": "YM=F", "RTY": "RTY=F",
           "GC": "GC=F", "CL": "CL=F", "6E": "6E=F", "ZN": "ZN=F"}
EQUITY_INDEX_FUTURES = {"ES", "MES", "NQ", "MNQ", "YM", "RTY"}       # quarterly expiry rule known (third Friday)
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
    for s in STOCKS + ETFS:
        i = book.add(Instrument(f"US:{s}", MarketType.ETF if s in ETFS else MarketType.STOCK, s, "US", "USD",
                                tick_size=D("0.01"), quantity_step=D(1), min_quantity=D(1), calendar="XNYS",
                                data_source="yahoo"))
        src[i.instrument_id] = DataSource("yahoo", s, "Yahoo Finance chart data (unofficial; split/dividend adjusted)")
    for p in FX:
        jpy = p.endswith("JPY")
        i = book.add(Instrument(f"FX:{p}", MarketType.FX_OTC, p, "FX", p[3:], tick_size=D("0.001" if jpy else "0.00001"),
                                quantity_step=D(1000), min_quantity=D(1000), base_asset=p[:3], quote_asset=p[3:],
                                calendar="FX", data_source="yahoo", tags=("reference_mid_no_dealer_quotes",)))
        src[i.instrument_id] = DataSource("yahoo", f"{p}=X", "reference mid price, not a dealer's bid/ask")
    for name, ysym in INDICES.items():
        i = book.add(Instrument(f"INDEX:{name}", MarketType.INDEX_REFERENCE, name, "INDEX", "USD",
                                settlement=Settlement.NONE, calendar="XNYS", data_source="yahoo"))
        src[i.instrument_id] = DataSource("yahoo", ysym, "calculated index: a reference, never ordered")
    specs = load_specs()
    for root, ysym in FUTURES.items():
        f = future_from_spec(root, specs)
        tags = ("continuous_provider_series",) + (("quarterly_roll_rule",) if root in EQUITY_INDEX_FUTURES else
                                                  ("research_only_no_contract_data",))
        f = replace(f, calendar="CME", data_source="yahoo", tags=tags)
        book.add(f)
        src[f.instrument_id] = DataSource("yahoo", ysym, "provider's continuous front-month series: roll jumps included")
    for d in DEMO:
        i = book.add(Instrument(f"DEMO:{d}", MarketType.CRYPTO_SPOT, d, "DEMO", "USD", tick_size=D("0.01"),
                                quantity_step=D("0.0001"), min_quantity=D("0.0001"), calendar="CRYPTO",
                                data_source="demo", tags=("simulated",)))
        src[i.instrument_id] = DataSource("demo", d, "SIMULATED prices for offline use: not a real market")
    return book, src


def paper_tradable(inst: Instrument) -> tuple[bool, str]:
    """Whether the paper engine may trade this instrument, and why not."""
    if not inst.tradable:
        return False, "an index is a calculated reference: trade one of its proxies (" + \
            ", ".join(INDEX_REFERENCES.get(inst.symbol, [])) + ")"
    if "research_only_no_contract_data" in inst.tags:
        return False, ("no contract-level data or roll calendar for this future: research only until a futures data "
                       "feed is connected (REQUIRES CONNECTION)")
    return True, "ok"
