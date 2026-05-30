import sqlite3
import os
import math

_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "uk_equity_library.db")

# CAPM constants
RF          = 0.044   # UK risk-free rate
MIN_HISTORY = 36      # minimum monthly price records required
MAX_WEIGHT  = 0.15    # maximum weight per stock
MIN_WEIGHT  = 0.01    # minimum weight if included (avoids negligible allocations)
N_PORTFOLIOS = 5000   # Monte Carlo simulations for efficient frontier


def _get_returns(tickers, start_year="2015"):
    """
    Pull monthly adj_close prices from DB and compute monthly returns.
    Returns dict {ticker: [monthly_return, ...]} aligned to common dates.
    """
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row

    # Pull prices for all tickers from start_year onwards
    price_data = {}
    for ticker in tickers:
        rows = conn.execute("""
            SELECT date, adj_close FROM prices
            WHERE ticker = ? AND date >= ? AND adj_close IS NOT NULL AND adj_close > 0
            ORDER BY date ASC
        """, (ticker, f"{start_year}-01-01")).fetchall()
        if len(rows) >= MIN_HISTORY:
            price_data[ticker] = {r["date"]: r["adj_close"] for r in rows}

    conn.close()

    if not price_data:
        return {}

    # Find common dates across all tickers
    date_sets = [set(v.keys()) for v in price_data.values()]
    common_dates = sorted(set.intersection(*date_sets))

    if len(common_dates) < MIN_HISTORY:
        return {}

    # Compute monthly returns on common dates
    returns = {}
    for ticker, prices in price_data.items():
        px = [prices[d] for d in common_dates]
        ret = [(px[i] - px[i-1]) / px[i-1] for i in range(1, len(px))]
        returns[ticker] = ret

    return returns


def _mean(values):
    return sum(values) / len(values)


def _variance(values):
    m = _mean(values)
    return sum((x - m) ** 2 for x in values) / len(values)


def _covariance(x, y):
    mx, my = _mean(x), _mean(y)
    return sum((x[i] - mx) * (y[i] - my) for i in range(len(x))) / len(x)


def _portfolio_performance(weights, tickers, returns):
    """Compute annualised return, volatility, and Sharpe for a set of weights."""
    n = len(returns[tickers[0]])

    # Weighted monthly return series
    port_returns = []
    for i in range(n):
        r = sum(weights[j] * returns[tickers[j]][i] for j in range(len(tickers)))
        port_returns.append(r)

    ann_return = _mean(port_returns) * 12
    ann_vol    = math.sqrt(_variance(port_returns) * 12)
    sharpe     = (ann_return - RF) / ann_vol if ann_vol > 0 else 0

    return ann_return, ann_vol, sharpe


def _random_weights(n, max_w=MAX_WEIGHT, min_w=MIN_WEIGHT):
    """Generate random valid weights summing to 1 with per-stock caps."""
    import random
    for _ in range(1000):
        w = [random.uniform(min_w, max_w) for _ in range(n)]
        total = sum(w)
        w = [x / total for x in w]
        if all(x <= max_w for x in w):
            return w
    # Fallback — equal weight
    return [1.0 / n] * n


def markowitz(tickers, start_year="2015"):
    """
    Monte Carlo Markowitz optimisation — max Sharpe portfolio.

    Args:
        tickers:    list of tickers to optimise across
        start_year: start of price history window

    Returns dict with:
        weights         — {ticker: weight} for max Sharpe portfolio
        ann_return      — annualised expected return
        ann_vol         — annualised volatility
        sharpe          — Sharpe ratio
        n_stocks        — number of stocks included
        frontier        — list of (vol, ret, sharpe) for all simulated portfolios
        excluded        — tickers dropped due to insufficient price history
    """
    returns = _get_returns(tickers, start_year)

    valid_tickers   = list(returns.keys())
    excluded        = [t for t in tickers if t not in returns]

    if len(valid_tickers) < 2:
        return {
            "weights": {}, "ann_return": None, "ann_vol": None,
            "sharpe": None, "n_stocks": 0,
            "frontier": [], "excluded": excluded,
            "note": "Insufficient price history for optimisation"
        }

    n = len(valid_tickers)
    best_sharpe = -999
    best_weights = None
    frontier = []

    for _ in range(N_PORTFOLIOS):
        w = _random_weights(n)
        ann_ret, ann_vol, sharpe = _portfolio_performance(w, valid_tickers, returns)
        frontier.append((round(ann_vol, 6), round(ann_ret, 6), round(sharpe, 6)))
        if sharpe > best_sharpe:
            best_sharpe = sharpe
            best_weights = w

    weights = {valid_tickers[i]: round(best_weights[i], 6) for i in range(n)}
    ann_ret, ann_vol, sharpe = _portfolio_performance(best_weights, valid_tickers, returns)

    return {
        "weights":    weights,
        "ann_return": round(ann_ret * 100, 2),
        "ann_vol":    round(ann_vol * 100, 2),
        "sharpe":     round(sharpe, 4),
        "n_stocks":   n,
        "frontier":   frontier,
        "excluded":   excluded,
        "note":       None,
    }


def print_markowitz(result):
    print(f"\n{'='*50}")
    print(f"  Markowitz Max-Sharpe Portfolio")
    print(f"{'='*50}")
    if result["note"]:
        print(f"  Note: {result['note']}")
        return
    print(f"  Stocks included:   {result['n_stocks']}")
    print(f"  Expected Return:   {result['ann_return']}% p.a.")
    print(f"  Volatility:        {result['ann_vol']}% p.a.")
    print(f"  Sharpe Ratio:      {result['sharpe']}")
    if result["excluded"]:
        print(f"  Excluded (no history): {', '.join(result['excluded'][:10])}"
              + (f" + {len(result['excluded'])-10} more" if len(result['excluded']) > 10 else ""))
    print()
    print(f"  {'Ticker':<12} {'Weight':>8}")
    print(f"  {'-'*22}")
    # Only show stocks with meaningful weight (>= 0.5%)
    shown = {t: w for t, w in result["weights"].items() if w >= 0.005}
    for ticker, weight in sorted(shown.items(), key=lambda x: -x[1]):
        print(f"  {ticker:<12} {weight*100:>7.2f}%")
    print(f"  {'-'*22}")
    print(f"  {'Total shown':<12} {sum(shown.values())*100:>7.2f}%")
    print()
