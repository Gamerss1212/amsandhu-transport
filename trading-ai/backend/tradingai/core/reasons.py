"""Reason codes (owner's specification, section 5F): one vocabulary for why a strategy is inactive, why research
rejected it, and why the risk service blocked an order. The UI and the assistant show the code and its meaning."""

REASON_CODES = {
    "INSUFFICIENT_DATA": "not enough data (history, sample size or a required feed) to decide",
    "SOURCE_METHOD_UNVERIFIED": "the published method was not replicated; this is an adaptation or the universe is "
                                "biased (for example survivorship)",
    "EDGE_UNCERTAIN": "the measured edge is not distinguishable from luck after counting every trial",
    "COSTS_TOO_HIGH": "trading costs remove the edge (or the spread is too wide)",
    "CAPACITY_EXCEEDED": "the order is too large for the market's traded volume",
    "REGIME_UNSUITABLE": "current market conditions are outside where the strategy is meant to work",
    "RELATIONSHIP_BROKEN": "a pair or spread relationship failed its diagnostics",
    "BORROW_UNAVAILABLE": "shorting or borrowing is not available for this product here",
    "FUNDING_UNFAVORABLE": "financing or funding costs exceed the expected carry (or funding data is missing)",
    "PRODUCT_UNSUPPORTED": "the product (options, bonds, dated contracts, order books...) is not supported by any "
                           "connected data source or broker adapter",
    "PERMISSION_MISSING": "the account or broker does not permit this product or access (for example ETF creation)",
    "STALE_DATA": "the newest data is too old to act on",
    "HEDGE_INCOMPLETE": "a hedge leg is missing or could not be sized",
    "PORTFOLIO_LIMIT": "a portfolio risk limit (position, exposure, leverage, concentration...) would be exceeded",
    # additions used by this software
    "ENTRIES_PAUSED": "the owner paused new entries; exits and position management continue",
    "KILL_SWITCH": "STOP ALL TRADING is engaged",
    "TRADING_LOCKED": "a daily/weekly loss or drawdown limit locked trading",
    "MARKET_CLOSED": "the market is closed",
    "RECONCILIATION_REQUIRED": "local records and the broker disagree; new exposure is frozen",
    "INVALID_ORDER": "the order itself is malformed (quantity, side, price, account or duplicate)",
    "CONTRACT_TOO_LARGE": "one contract (or lot) is bigger than the position this capital and sizing allow, so "
                          "signals could not be traded; a micro contract or more capital is needed",
}

# risk-service checks and research gates -> reason code
_BY_CHECK = {
    "data fresh": "STALE_DATA", "broker permits this product": "PERMISSION_MISSING",
    "instrument tradable": "PRODUCT_UNSUPPORTED", "known market": "PRODUCT_UNSUPPORTED",
    "position limit": "PORTFOLIO_LIMIT", "gross exposure": "PORTFOLIO_LIMIT", "leverage": "PORTFOLIO_LIMIT",
    "asset-class exposure": "PORTFOLIO_LIMIT", "correlated exposure": "PORTFOLIO_LIMIT",
    "open positions": "PORTFOLIO_LIMIT", "order size": "PORTFOLIO_LIMIT", "liquidity": "CAPACITY_EXCEEDED",
    "spread": "COSTS_TOO_HIGH", "new entries allowed": "ENTRIES_PAUSED", "kill switch not engaged": "KILL_SWITCH",
    "trading not locked": "TRADING_LOCKED", "market open": "MARKET_CLOSED", "reconciliation clean":
    "RECONCILIATION_REQUIRED", "account validated": "PERMISSION_MISSING", "broker connected": "PERMISSION_MISSING",
    "no event restriction": "REGIME_UNSUITABLE", "positive quantity": "INVALID_ORDER", "valid side": "INVALID_ORDER",
    "valid price": "INVALID_ORDER", "price within band": "INVALID_ORDER", "quantity matches the sized target":
    "INVALID_ORDER", "not a duplicate": "INVALID_ORDER", "order rate": "PORTFOLIO_LIMIT", "positive equity":
    "PORTFOLIO_LIMIT", "valid contract multiplier": "INVALID_ORDER", "reduce-only claim verified": "INVALID_ORDER",
    "shrunk quantity above zero": "PORTFOLIO_LIMIT", "held-out rebalances": "INSUFFICIENT_DATA", "test trades": "INSUFFICIENT_DATA",
    "held-out net return positive": "EDGE_UNCERTAIN", "test net return positive": "EDGE_UNCERTAIN",
    "deflated Sharpe": "EDGE_UNCERTAIN", "deflated Sharpe (held-out)": "EDGE_UNCERTAIN",
    "held-out Sharpe at 2x costs": "COSTS_TOO_HIGH", "Sharpe at 2x costs": "COSTS_TOO_HIGH",
    "walk-forward OOS Sharpe": "EDGE_UNCERTAIN", "OOS / IS Sharpe": "EDGE_UNCERTAIN", "PBO": "EDGE_UNCERTAIN",
    "parameter stability": "EDGE_UNCERTAIN", "net without the 5 best trades": "EDGE_UNCERTAIN",
    "beats random placebo": "EDGE_UNCERTAIN", "beats shifted placebo": "EDGE_UNCERTAIN",
}


def code_for(check_name: str) -> str | None:
    if check_name in _BY_CHECK:
        return _BY_CHECK[check_name]
    for k, v in _BY_CHECK.items():
        if check_name.startswith(k):
            return v
    return None
