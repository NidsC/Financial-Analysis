"""
ScoreDCS Backtester — Quarterly rebalancing, annual scoring, 2016–2025.

Platform:   Hargreaves Lansdown — £11.95 commission per trade
Stamp duty: 0.5% on all purchases
CGT:        24% on net gains (higher-rate taxpayer); losses offset gains (tax-loss harvesting)
Dividends:  Taxed at UK higher-rate dividend tax (33.75% above allowance);
            collected and reinvested at each quarterly rebalance
Rebalancing:
  May    (full)    — re-score universe, rebuild eligible list, set new target weights
  Aug/Nov/Feb      — price-only rebalance back to May target weights
                     Stop-loss: exit any stock down >STOP_LOSS_PCT from May entry price
                     Stop-loss cash parked in gilts (BoE base rate) until next May
Starting capital: £1,000,000 (2016)

Universe: Stocks screened at £300M+ market cap at any point 2011–2026.
          This excludes micro-caps that were never investable at scale, which
          substantially mitigates survivorship bias versus an unconstrained screen.
"""

import sqlite3
import os
import math
import random

_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "uk_equity_library.db")

# ── Costs & Tax ──────────────────────────────────────────────────────────────
COMMISSION        = 11.95    # £ per trade (buy or sell)
STAMP_DUTY        = 0.005    # 0.5% on purchases
CGT_RATE          = 0.24     # 24% on net capital gains
CGT_ALLOWANCE     = 3000.0   # £3,000 annual CGT allowance (2024/25)
DIV_TAX_RATE      = 0.3375   # 33.75% (higher-rate dividend tax above allowance)
DIV_ALLOWANCE     = 500.0    # £500 annual dividend allowance (2024/25)

# ── Strategy parameters ───────────────────────────────────────────────────────
STARTING_CAPITAL  = 1_000_000.0
TOP_N             = 32       # portfolio size (top-N scoring stocks)
MIN_SCORE         = 67.0     # minimum ScoreDCS score to be eligible
MAX_WEIGHT        = 0.15     # max weight per stock (score-weighted)
MIN_YEARS_YIELD   = 5        # universe filter: years of div yield history
AVG_YIELD_MIN     = 0.04     # universe filter: avg div yield >= 4%
MAX_YIELD_PER_YR  = 0.25     # universe filter: cap artefact yields
MIN_MKTCAP_GBX    = 30_000_000_000  # £300M in GBX — excludes uninvestable micro-caps

# ── Quarterly rebalancing parameters ─────────────────────────────────────────
STOP_LOSS_PCT     = 0.20     # exit stock if down >20% from May entry price
# Quarterly rebalance months: May=full, Aug/Nov/Feb=price-only
FULL_REBAL_MONTH  = "05"
INTERIM_MONTHS    = ["08", "11", "02"]   # Aug, Nov, Feb

# ── BoE base rate by year (annual) — gilt proxy for stop-loss cash ────────────
# Source: Bank of England published rate history
BOE_RATE = {
    2016: 0.0025,   # 0.25%
    2017: 0.0050,   # 0.50%
    2018: 0.0075,   # 0.75%
    2019: 0.0075,   # 0.75%
    2020: 0.0010,   # 0.10% (emergency cut)
    2021: 0.0010,   # 0.10%
    2022: 0.0175,   # avg ~1.75% (rose 0.25→3.5%)
    2023: 0.0450,   # avg ~4.50% (rose to 5.25%)
    2024: 0.0500,   # avg ~5.00%
    2025: 0.0450,   # avg ~4.50% (cutting cycle)
}

# ── RF & return model ─────────────────────────────────────────────────────────
RF  = 0.044
ERP = 0.046
N_PORTFOLIOS = 3000   # Monte Carlo for Markowitz (lower for speed)

# ── FTSE 100 Total Return (annual, including dividends) ───────────────────────
# Source: Bloomberg / LSEG historical data (approximate, widely published figures)
FTSE100_ANNUAL_TR = {
    2016: 0.1943,   # +19.4%
    2017: 0.1180,   # +11.8%
    2018: -0.0915,  # -9.2%
    2019: 0.1749,   # +17.5%
    2020: -0.1164,  # -11.6%
    2021: 0.1870,   # +18.7%
    2022: 0.0448,   # +4.5%
    2023: 0.0788,   # +7.9%
    2024: 0.0553,   # +5.5%
    2025: -0.02,    # YTD estimate (partial year)
}

BACKTEST_YEARS = list(range(2016, 2026))


# ══════════════════════════════════════════════════════════════════════════════
#  DATA ACCESS — point-in-time
# ══════════════════════════════════════════════════════════════════════════════

def _get_pit_universe(rebalance_year):
    """
    Universe of tickers with sufficient dividend history as of rebalance_year.
    Uses fundamentals data up to and including rebalance_year-1 (prior year known at Jan rebalance).
    """
    data_year = str(rebalance_year - 1)
    conn = sqlite3.connect(_DB_PATH)
    rows = conn.execute("""
        SELECT f.ticker FROM fundamentals f
        JOIN companies c ON f.ticker = c.ticker
        WHERE f.dividend_yield IS NOT NULL
          AND f.dividend_yield > 0
          AND f.dividend_yield <= ?
          AND f.year <= ?
          AND c.market_cap >= ?
        GROUP BY f.ticker
        HAVING COUNT(f.year) >= ?
           AND AVG(f.dividend_yield) >= ?
           AND SUM(CASE WHEN f.year = ? THEN 1 ELSE 0 END) > 0
        ORDER BY AVG(f.dividend_yield) DESC
    """, (MAX_YIELD_PER_YR, data_year, MIN_MKTCAP_GBX, MIN_YEARS_YIELD, AVG_YIELD_MIN, data_year)).fetchall()
    conn.close()
    return [r[0] for r in rows]


def _get_pit_score(ticker, rebalance_year):
    """
    Score ticker using fundamentals data available at rebalance_year (year-1 data).
    Returns total_score (0-100) or None.
    """
    data_year = str(rebalance_year - 1)
    prev_year = str(rebalance_year - 2)

    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row

    fund = conn.execute("""
        SELECT fcf_yield, payout_ratio, roe, roic
        FROM fundamentals WHERE ticker = ? AND year = ?
    """, (ticker, data_year)).fetchone()

    fin = conn.execute("""
        SELECT net_income, ebitda, ebit, total_debt
        FROM financials WHERE ticker = ? AND year = ?
    """, (ticker, data_year)).fetchone()

    fin_prev = conn.execute("""
        SELECT net_income FROM financials WHERE ticker = ? AND year = ?
    """, (ticker, prev_year)).fetchone()

    conn.close()

    if fund is None:
        return None

    fcf_yield = fund["fcf_yield"]
    payout    = fund["payout_ratio"]
    roe       = fund["roe"]
    roic      = fund["roic"]

    # FCF Yield score
    if fcf_yield is None:
        fcfpoint = 2
    elif fcf_yield >= 0.08:
        fcfpoint = 4
    elif fcf_yield >= 0.05:
        fcfpoint = 3
    elif fcf_yield >= 0.02:
        fcfpoint = 2
    elif fcf_yield > 0:
        fcfpoint = 1
    else:
        fcfpoint = 0

    # Payout ratio score
    if payout is None:
        paypoint = 2
    elif payout > 1:
        paypoint = 0
    elif payout >= 0.85:
        paypoint = 2
    elif payout >= 0.7:
        paypoint = 3
    elif payout >= 0.4:
        paypoint = 4
    elif payout >= 0.25:
        paypoint = 3
    elif payout > 0.1:
        paypoint = 2
    else:
        paypoint = 1

    # DGR proxy (net income growth)
    if fin and fin_prev and fin["net_income"] and fin_prev["net_income"] and fin_prev["net_income"] != 0:
        dgr = (fin["net_income"] - fin_prev["net_income"]) / abs(fin_prev["net_income"])
    else:
        dgr = None

    if dgr is None:
        dgrpoint = 1
    elif dgr >= 0.06:
        dgrpoint = 4
    elif dgr >= 0.04:
        dgrpoint = 3
    elif dgr >= 0.02:
        dgrpoint = 2
    elif dgr >= 0:
        dgrpoint = 1
    else:
        dgrpoint = 0

    # Leverage
    debt   = fin["total_debt"]  if fin else None
    ebitda = fin["ebitda"]      if fin else None
    if debt is None or ebitda is None:
        levpoint = 2
    elif debt <= 0:
        levpoint = 5
    elif ebitda <= 0:
        levpoint = 0
    else:
        lev = debt / ebitda
        if lev <= 1.5:   levpoint = 5
        elif lev <= 2.5: levpoint = 4
        elif lev <= 3.5: levpoint = 3
        elif lev <= 5:   levpoint = 2
        elif lev <= 7:   levpoint = 1
        else:            levpoint = 0

    # Coverage (EBIT/EBITDA proxy)
    ebit = fin["ebit"] if fin else None
    if ebit is None or ebitda is None:
        coverpoint = 2
    elif ebit <= 0:
        coverpoint = 0
    elif ebitda <= 0:
        coverpoint = 2
    else:
        cov = ebit / ebitda
        if cov >= 0.9:   coverpoint = 4
        elif cov >= 0.7: coverpoint = 3
        elif cov >= 0.5: coverpoint = 2
        elif cov >= 0.3: coverpoint = 1
        else:            coverpoint = 0

    # ROE
    if roe is None:     roepoint = 2
    elif roe >= 0.2:    roepoint = 5
    elif roe >= 0.15:   roepoint = 4
    elif roe >= 0.1:    roepoint = 3
    elif roe >= 0.05:   roepoint = 2
    elif roe >= 0:      roepoint = 1
    else:               roepoint = 0

    # ROIC
    if roic is None:    roicpoint = 2
    elif roic >= 0.2:   roicpoint = 4
    elif roic >= 0.15:  roicpoint = 3
    elif roic >= 0.1:   roicpoint = 2
    elif roic >= 0.05:  roicpoint = 1
    else:               roicpoint = 0

    total = dgrpoint + fcfpoint + paypoint + levpoint + coverpoint + roepoint + roicpoint
    return round((total / 30) * 100, 2)


def _get_pit_div_yield(ticker, rebalance_year):
    """Dividend yield for year-1 (known at rebalance time)."""
    data_year = str(rebalance_year - 1)
    conn = sqlite3.connect(_DB_PATH)
    row = conn.execute("""
        SELECT dividend_yield FROM fundamentals
        WHERE ticker = ? AND year = ?
    """, (ticker, data_year)).fetchone()
    conn.close()
    return row[0] if row else None


def _get_price(ticker, year, month="01"):
    """
    Get adj_close price for ticker for the given calendar month (end-of-month convention).
    DB stores end-of-month prices (e.g. 2016-01-29). Searches full month then ±1 month.
    Returns price in GBX (pence) or None.
    """
    conn = sqlite3.connect(_DB_PATH)
    # Search the full target month
    row = conn.execute("""
        SELECT adj_close FROM prices
        WHERE ticker = ? AND strftime('%Y-%m', date) = ?
          AND adj_close IS NOT NULL AND adj_close > 0
        ORDER BY date DESC
        LIMIT 1
    """, (ticker, f"{year}-{month}")).fetchone()

    if row is None:
        # Try prior month as fallback
        m_int = int(month)
        if m_int == 1:
            prev_m, prev_y = "12", str(int(year) - 1)
        else:
            prev_m, prev_y = str(m_int - 1).zfill(2), str(year)
        row = conn.execute("""
            SELECT adj_close FROM prices
            WHERE ticker = ? AND strftime('%Y-%m', date) = ?
              AND adj_close IS NOT NULL AND adj_close > 0
            ORDER BY date DESC
            LIMIT 1
        """, (ticker, f"{prev_y}-{prev_m}")).fetchone()

    conn.close()
    return row[0] if row else None


def _get_monthly_returns(tickers, start_year, end_year):
    """
    Pull monthly adj_close prices for Markowitz optimisation.
    Returns dict {ticker: [monthly_return, ...]} aligned to common dates.
    """
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row

    price_data = {}
    for ticker in tickers:
        rows = conn.execute("""
            SELECT date, adj_close FROM prices
            WHERE ticker = ? AND date >= ? AND date <= ?
              AND adj_close IS NOT NULL AND adj_close > 0
            ORDER BY date ASC
        """, (ticker, f"{start_year}-01-01", f"{end_year}-12-31")).fetchall()
        if len(rows) >= 36:
            price_data[ticker] = {r["date"]: r["adj_close"] for r in rows}

    conn.close()

    if not price_data:
        return {}

    date_sets = [set(v.keys()) for v in price_data.values()]
    common_dates = sorted(set.intersection(*date_sets))
    if len(common_dates) < 36:
        return {}

    returns = {}
    for ticker, prices in price_data.items():
        px = [prices[d] for d in common_dates]
        returns[ticker] = [(px[i] - px[i-1]) / px[i-1] for i in range(1, len(px))]

    return returns


# ══════════════════════════════════════════════════════════════════════════════
#  PORTFOLIO CONSTRUCTION
# ══════════════════════════════════════════════════════════════════════════════

def _build_score_weighted(scored_tickers):
    """
    Build score-weighted target weights from (ticker, score) list.
    Returns {ticker: weight}.
    """
    eligible = [(t, s) for t, s in scored_tickers if s is not None and s >= MIN_SCORE]
    if not eligible:
        return {}

    eligible = sorted(eligible, key=lambda x: -x[1])[:TOP_N]
    weights = {t: s for t, s in eligible}

    for _ in range(100):
        total = sum(weights.values())
        if total == 0:
            break
        normalised = {t: w / total for t, w in weights.items()}
        excess = sum(v - MAX_WEIGHT for v in normalised.values() if v > MAX_WEIGHT)
        if excess < 1e-9:
            weights = {t: min(v, MAX_WEIGHT) for t, v in normalised.items()}
            break
        uncapped = {t: weights[t] for t in weights if normalised[t] < MAX_WEIGHT}
        uncapped_total = sum(uncapped.values())
        for t in weights:
            if t in uncapped:
                weights[t] = weights[t] + (weights[t] / uncapped_total) * excess * total
            else:
                weights[t] = MAX_WEIGHT * total

    total = sum(weights.values())
    return {t: w / total for t, w in weights.items()}


def _mean(v): return sum(v) / len(v)
def _variance(v): m = _mean(v); return sum((x-m)**2 for x in v) / len(v)


def _portfolio_perf(w, tickers, returns):
    n = len(returns[tickers[0]])
    port = [sum(w[j] * returns[tickers[j]][i] for j in range(len(tickers))) for i in range(n)]
    ann_ret = _mean(port) * 12
    ann_vol = math.sqrt(_variance(port) * 12)
    sharpe  = (ann_ret - RF) / ann_vol if ann_vol > 0 else 0
    return ann_ret, ann_vol, sharpe


def _random_weights(n):
    min_w, max_w = 0.01, MAX_WEIGHT
    for _ in range(1000):
        w = [random.uniform(min_w, max_w) for _ in range(n)]
        total = sum(w)
        w = [x / total for x in w]
        if all(x <= max_w for x in w):
            return w
    return [1.0 / n] * n


def _build_markowitz(tickers, rebalance_year):
    """
    Point-in-time Markowitz: use price history up to start of rebalance_year.
    Returns {ticker: weight} or {} if insufficient data.
    """
    returns = _get_monthly_returns(tickers, rebalance_year - 5, rebalance_year - 1)
    valid = list(returns.keys())

    if len(valid) < 2:
        return {}

    n = len(valid)
    best_sharpe, best_w = -999, None

    for _ in range(N_PORTFOLIOS):
        w = _random_weights(n)
        _, _, sh = _portfolio_perf(w, valid, returns)
        if sh > best_sharpe:
            best_sharpe, best_w = sh, w

    if best_w is None:
        return {}

    return {valid[i]: best_w[i] for i in range(n)}


# ══════════════════════════════════════════════════════════════════════════════
#  COST CALCULATIONS
# ══════════════════════════════════════════════════════════════════════════════

def _buy_cost(value):
    """Total cost of a purchase: stamp duty + commission."""
    return value * STAMP_DUTY + COMMISSION


def _sell_cost(_value):
    """Cost of a sale: commission only (no stamp duty on sales)."""
    return COMMISSION


def _calc_cgt(gains, losses, cgt_allowance_used):
    """
    Calculate CGT payable after netting losses against gains.
    Returns (tax_payable, remaining_allowance_used).
    """
    net_gain = gains - losses
    remaining_allowance = max(0, CGT_ALLOWANCE - cgt_allowance_used)
    taxable = max(0, net_gain - remaining_allowance)
    tax = taxable * CGT_RATE
    allowance_consumed = min(remaining_allowance, max(0, net_gain))
    return tax, cgt_allowance_used + allowance_consumed


def _calc_div_tax(gross_div, div_allowance_used):
    """
    Calculate dividend tax payable.
    Returns (net_dividend, allowance_used).
    """
    remaining_allowance = max(0, DIV_ALLOWANCE - div_allowance_used)
    taxable = max(0, gross_div - remaining_allowance)
    tax = taxable * DIV_TAX_RATE
    return gross_div - tax, div_allowance_used + min(remaining_allowance, gross_div)


# ══════════════════════════════════════════════════════════════════════════════
#  CORE SIMULATION
# ══════════════════════════════════════════════════════════════════════════════

def _rebalance(portfolio, cash, target_weights, prices, cgt_allowance_used):
    """
    Rebalance portfolio to target_weights given current cash balance.

    The rebalance allocates (portfolio_equity + cash) across target_weights.
    Sells generate cash; buys consume cash; all costs deducted from cash.

    Args:
        portfolio:      {ticker: {'shares': float, 'cost_basis': float}} in GBX
        cash:           float (£) — available cash before rebalance
        target_weights: {ticker: float} — desired fractional allocation
        prices:         {ticker: price_gbx}
        cgt_allowance_used: float

    Returns:
        (new_portfolio, new_cash, commission_costs, cgt_paid, cgt_allowance_used)
    """
    commission_costs = 0.0
    cgt_paid         = 0.0

    # Current equity value in £
    equity = sum(h["shares"] * prices[t] / 100
                 for t, h in portfolio.items() if t in prices and prices[t])
    total_nav = equity + cash

    # Target value per stock
    target_values = {t: w * total_nav for t, w in target_weights.items()}

    # Current stock values in £
    current_values = {t: h["shares"] * prices.get(t, 0) / 100
                      for t, h in portfolio.items()}

    all_tickers = set(portfolio.keys()) | set(target_weights.keys())
    sells, buys = [], []
    for t in all_tickers:
        cur = current_values.get(t, 0.0)
        tgt = target_values.get(t, 0.0)
        diff = tgt - cur
        if diff < -50:
            sells.append((t, abs(diff)))
        elif diff > 50:
            buys.append((t, diff))

    new_portfolio = {t: {"shares": h["shares"], "cost_basis": h["cost_basis"]}
                     for t, h in portfolio.items()}
    gains  = 0.0
    losses = 0.0

    # Process sells first — raise cash
    for ticker, sell_val in sells:
        p = prices.get(ticker)
        if not p:
            continue
        price_gbp = p / 100
        holding = new_portfolio.get(ticker)
        if not holding:
            continue

        shares_to_sell = min(sell_val / price_gbp, holding["shares"])
        gross_proceeds = shares_to_sell * price_gbp
        comm = COMMISSION
        commission_costs += comm
        net_proceeds = gross_proceeds - comm
        cash += net_proceeds

        cost_basis_gbp = shares_to_sell * holding["cost_basis"] / 100
        gain = net_proceeds - cost_basis_gbp
        if gain > 0:
            gains += gain
        else:
            losses += abs(gain)

        holding["shares"] -= shares_to_sell
        if holding["shares"] < 0.001:
            del new_portfolio[ticker]

    # Apply CGT on net gains
    cgt, cgt_allowance_used = _calc_cgt(gains, losses, cgt_allowance_used)
    cgt_paid = cgt
    cash -= cgt

    # Process buys — spend cash
    for ticker, buy_val in buys:
        p = prices.get(ticker)
        if not p:
            continue
        price_gbp = p / 100

        # Cap buy to available cash (leave small buffer for rounding)
        affordable = min(buy_val, cash - COMMISSION - 10)
        if affordable <= COMMISSION:
            continue

        stamp = affordable * STAMP_DUTY
        comm  = COMMISSION
        total_cost = stamp + comm
        commission_costs += total_cost
        actual_invested = affordable - total_cost
        if actual_invested <= 0:
            continue

        shares_bought = actual_invested / price_gbp
        cash -= affordable  # deduct the full buy amount (commission inside)

        if ticker in new_portfolio:
            existing = new_portfolio[ticker]
            total_sh = existing["shares"] + shares_bought
            blended  = (existing["shares"] * existing["cost_basis"] + shares_bought * p) / total_sh
            new_portfolio[ticker] = {"shares": total_sh, "cost_basis": blended}
        else:
            new_portfolio[ticker] = {"shares": shares_bought, "cost_basis": p}

    return new_portfolio, cash, commission_costs, cgt_paid, cgt_allowance_used


def _portfolio_value(portfolio, prices):
    """Compute portfolio value in £ from holdings."""
    total = 0.0
    for ticker, h in portfolio.items():
        p = prices.get(ticker)
        if p:
            total += h["shares"] * p / 100  # GBX → £
    return total


def _collect_dividends(portfolio, prices, div_yields, cash, div_allowance_used):
    """
    Collect annual dividends, tax them, redistribute net dividend as cash.
    div_yields: {ticker: float} — annual div yield as decimal

    Returns (gross_div, net_div, div_tax, div_allowance_used)
    """
    gross_div = 0.0
    for ticker, h in portfolio.items():
        p = prices.get(ticker)
        dy = div_yields.get(ticker)
        if p and dy:
            stock_value_gbp = h["shares"] * p / 100
            gross_div += stock_value_gbp * dy

    net_div, div_allowance_used = _calc_div_tax(gross_div, div_allowance_used)
    div_tax = gross_div - net_div
    return gross_div, net_div, div_tax, div_allowance_used


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN BACKTEST LOOP
# ══════════════════════════════════════════════════════════════════════════════

def _quarterly_interim_rebalance(portfolio, cash, gilt_cash, target_weights,
                                  entry_prices, q_month, q_year,
                                  cgt_allowance_used, div_allowance_used,
                                  annual_year, div_yields):
    """
    Interim quarterly rebalance (Aug / Nov / Feb):
      1. Collect proportional quarterly dividends (annual yield / 4)
      2. Apply stop-loss: exit stocks down >STOP_LOSS_PCT from May entry — proceeds to gilt
      3. Rebalance survivors back to target weights using current prices
      4. Gilt cash earns BoE rate for one quarter

    Returns: (portfolio, cash, gilt_cash, comm_costs, cgt_paid,
               cgt_allowance_used, div_allowance_used, gross_div_q, div_tax_q,
               stops_triggered)
    """
    q_prices = {}
    for t in set(list(portfolio.keys()) + list(target_weights.keys())):
        p = _get_price(t, q_year, q_month)
        if p:
            q_prices[t] = p

    # 1. Quarterly dividends (¼ of annual yield on current holding value)
    gross_div_q = 0.0
    for t, h in portfolio.items():
        p  = q_prices.get(t)
        dy = div_yields.get(t)
        if p and dy:
            gross_div_q += h["shares"] * p / 100 * (dy / 4)

    net_div_q, div_allowance_used = _calc_div_tax(gross_div_q, div_allowance_used)
    div_tax_q = gross_div_q - net_div_q
    cash += net_div_q

    # 2. Stop-loss: exit positions down >STOP_LOSS_PCT from May entry price
    gains, losses = 0.0, 0.0
    comm_costs = 0.0
    stops_triggered = []
    new_portfolio = {t: {"shares": h["shares"], "cost_basis": h["cost_basis"]}
                     for t, h in portfolio.items()}

    for t, h in portfolio.items():
        entry_p = entry_prices.get(t)
        curr_p  = q_prices.get(t)
        if not entry_p or not curr_p:
            continue
        drop = (curr_p - entry_p) / entry_p
        if drop < -STOP_LOSS_PCT:
            # Full exit
            price_gbp    = curr_p / 100
            gross_proc   = h["shares"] * price_gbp
            comm         = COMMISSION
            comm_costs  += comm
            net_proc     = gross_proc - comm
            gilt_cash   += net_proc          # parked in gilts

            cost_basis_gbp = h["shares"] * h["cost_basis"] / 100
            gain = net_proc - cost_basis_gbp
            if gain > 0: gains  += gain
            else:        losses += abs(gain)

            del new_portfolio[t]
            stops_triggered.append((t, round(drop * 100, 1)))

    # Apply CGT on stop-loss exits
    cgt, cgt_allowance_used = _calc_cgt(gains, losses, cgt_allowance_used)
    cash -= cgt
    comm_costs += cgt   # track as cost

    portfolio = new_portfolio

    # 3. Rebalance survivors back to target weights (exclude stopped-out tickers)
    active_targets = {t: w for t, w in target_weights.items() if t in portfolio or t not in stops_triggered}
    # Re-normalise weights after removals
    active_targets = {t: w for t, w in target_weights.items()
                      if t not in [s[0] for s in stops_triggered]}
    total_w = sum(active_targets.values())
    if total_w > 0:
        active_targets = {t: w / total_w for t, w in active_targets.items()}

    if active_targets:
        portfolio, cash, rebal_comm, rebal_cgt, cgt_allowance_used = _rebalance(
            portfolio, cash, active_targets, q_prices, cgt_allowance_used
        )
        comm_costs += rebal_comm + rebal_cgt

    # 4. Gilt cash grows at quarterly BoE rate
    quarterly_rate = BOE_RATE.get(annual_year, 0.005) / 4
    gilt_cash *= (1 + quarterly_rate)

    return (portfolio, cash, gilt_cash, comm_costs, cgt,
            cgt_allowance_used, div_allowance_used,
            gross_div_q, div_tax_q, stops_triggered)


def run_backtest(strategy="score_weighted", verbose=True):
    """
    Run quarterly backtester: full rebalance in May, price-only in Aug/Nov/Feb.
    Stop-loss exits parked in gilts at BoE base rate.

    Args:
        strategy: "score_weighted" or "markowitz"
        verbose:  print year-by-year results

    Returns dict with full performance history.
    """
    cash        = STARTING_CAPITAL
    gilt_cash   = 0.0               # stop-loss proceeds earning gilt rate
    portfolio   = {}
    nav_history = {}
    year_logs   = []

    cgt_allowance_used = 0.0
    div_allowance_used = 0.0

    total_cgt_paid   = 0.0
    total_div_tax    = 0.0
    total_costs      = 0.0
    total_gross_divs = 0.0

    for year in BACKTEST_YEARS:
        if verbose:
            print(f"\n── {year} {'─'*45}")

        # Reset annual tax allowances each April tax year end
        cgt_allowance_used = 0.0
        div_allowance_used = 0.0

        # ── FULL MAY REBALANCE ─────────────────────────────────────────────

        # Step 1: Universe and scoring
        universe = _get_pit_universe(year)
        if not universe:
            if verbose:
                print(f"  No universe for {year}, skipping.")
            continue

        scored = []
        for t in universe:
            sc = _get_pit_score(t, year)
            if sc is not None:
                scored.append((t, sc))

        eligible = [(t, s) for t, s in scored if s >= MIN_SCORE]
        eligible_sorted = sorted(eligible, key=lambda x: -x[1])[:TOP_N]

        if len(eligible_sorted) < 2:
            if verbose:
                print(f"  Too few eligible stocks ({len(eligible_sorted)}), skipping.")
            continue

        eligible_tickers = [t for t, _ in eligible_sorted]

        # Step 2: Target weights
        if strategy == "score_weighted":
            target_weights = _build_score_weighted(eligible_sorted)
        else:
            mz_weights = _build_markowitz(eligible_tickers, year)
            if not mz_weights:
                n = len(eligible_tickers)
                mz_weights = {t: 1.0 / n for t in eligible_tickers}
            target_weights = mz_weights

        if not target_weights:
            continue

        # Step 3: May prices
        may_prices = {}
        for t in set(list(portfolio.keys()) + list(target_weights.keys())):
            p = _get_price(t, year, FULL_REBAL_MONTH)
            if p:
                may_prices[t] = p

        # Step 4: Collect annual dividends from prior holdings
        div_yields = {}
        for t in portfolio:
            dy = _get_pit_div_yield(t, year)
            if dy:
                div_yields[t] = dy

        gross_div, net_div, div_tax, div_allowance_used = _collect_dividends(
            portfolio, may_prices, div_yields, cash, div_allowance_used
        )
        cash += net_div
        total_gross_divs += gross_div
        total_div_tax    += div_tax

        # Gilt cash also returns to portfolio at May full rebalance
        cash += gilt_cash
        gilt_cash = 0.0

        # Step 5: NAV before rebalance
        current_nav = _portfolio_value(portfolio, may_prices) + cash

        if verbose:
            print(f"  Universe: {len(universe)} | Eligible: {len(eligible_sorted)}")
            print(f"  NAV (May {year}): £{current_nav:,.0f} | Gross div: £{gross_div:,.0f} | Div tax: £{div_tax:,.0f}")

        # Step 6: Full rebalance
        portfolio, cash, may_comm, may_cgt, cgt_allowance_used = _rebalance(
            portfolio, cash, target_weights, may_prices, cgt_allowance_used
        )
        total_costs    += may_comm + may_cgt
        total_cgt_paid += may_cgt

        # Record May entry prices for stop-loss comparison
        entry_prices = {t: may_prices[t] for t in portfolio if t in may_prices}

        # Div yields for quarterly dividend collection (use same annual yield / 4)
        q_div_yields = {t: _get_pit_div_yield(t, year) or 0.0 for t in portfolio}

        year_comm  = may_comm
        year_cgt   = may_cgt
        year_stops = []
        all_stops  = []

        # ── INTERIM QUARTERLY REBALANCES ──────────────────────────────────
        # Aug = Q1 (month 08, same year)
        # Nov = Q2 (month 11, same year)
        # Feb = Q3 (month 02, year+1)
        quarters = [
            ("08", year,     "Aug"),
            ("11", year,     "Nov"),
            ("02", year + 1, "Feb"),
        ]

        for q_month, q_year_val, q_label in quarters:
            (portfolio, cash, gilt_cash,
             q_comm, q_cgt,
             cgt_allowance_used, div_allowance_used,
             gross_div_q, div_tax_q,
             stops) = _quarterly_interim_rebalance(
                portfolio, cash, gilt_cash, target_weights,
                entry_prices, q_month, q_year_val,
                cgt_allowance_used, div_allowance_used,
                year, q_div_yields
            )

            total_costs      += q_comm
            total_cgt_paid   += q_cgt
            total_gross_divs += gross_div_q
            total_div_tax    += div_tax_q
            year_comm        += q_comm
            year_cgt         += q_cgt
            all_stops.extend(stops)

            if verbose and stops:
                print(f"    {q_label} stop-loss exits: "
                      + ", ".join(f"{t}({d}%)" for t, d in stops))

        # ── YEAR-END (Apr year+1): snapshot before next May rebalance ─────
        end_prices = {}
        for t in portfolio:
            p = _get_price(t, year + 1, "04")
            if p:
                end_prices[t] = p

        end_nav = _portfolio_value(portfolio, end_prices) + cash + gilt_cash
        nav_history[year] = end_nav

        ann_ret  = (end_nav / current_nav - 1) if current_nav > 0 else 0.0
        ftse_ret = FTSE100_ANNUAL_TR.get(year, 0)

        # Per-stock holdings detail
        score_map = {t: s for t, s in eligible_sorted}
        holdings_detail = []
        for t, w in sorted(target_weights.items(), key=lambda x: -x[1]):
            entry_p = entry_prices.get(t)
            exit_p  = end_prices.get(t)
            stopped = t in [s[0] for s in all_stops]
            stk_ret = None
            if stopped:
                # Use stop-loss exit price (quarterly price when stopped)
                stk_ret_str = "STOPPED"
            elif entry_p and exit_p:
                stk_ret = round((exit_p / entry_p - 1) * 100, 2)
                stk_ret_str = f"{stk_ret:+.1f}%"
            else:
                stk_ret_str = "N/A"
            h = portfolio.get(t)
            value_end = (h["shares"] * exit_p / 100) if h and exit_p else 0.0
            holdings_detail.append({
                "ticker":     t,
                "score":      score_map.get(t),
                "weight":     round(w * 100, 2),
                "entry_p":    round(entry_p, 0) if entry_p else None,
                "exit_p":     round(exit_p, 0)  if exit_p and not stopped else None,
                "return_pct": stk_ret,
                "return_str": stk_ret_str,
                "value_end":  round(value_end, 0),
                "stopped":    stopped,
            })

        if verbose:
            print(f"  Commission+CGT: £{year_comm+year_cgt:,.0f} | "
                  f"Stop-losses: {len(all_stops)} | "
                  f"Gilt cash: £{gilt_cash:,.0f}")
            print(f"  End NAV (Apr {year+1}): £{end_nav:,.0f} | "
                  f"Return: {ann_ret*100:+.2f}% | FTSE: {ftse_ret*100:+.2f}%")

        year_logs.append({
            "year":          year,
            "universe_size": len(universe),
            "eligible":      len(eligible_sorted),
            "n_holdings":    len(portfolio),
            "start_nav":     round(current_nav, 2),
            "end_nav":       round(end_nav, 2),
            "ann_return":    round(ann_ret * 100, 2),
            "ftse_return":   round(ftse_ret * 100, 2),
            "gross_div":     round(gross_div, 2),
            "div_tax":       round(div_tax, 2),
            "comm_costs":    round(year_comm, 2),
            "cgt_paid":      round(year_cgt, 2),
            "stops":         all_stops,
            "gilt_cash":     round(gilt_cash, 2),
            "holdings":      holdings_detail,
        })

    # ── Final performance summary ──────────────────────────────────────────
    if not nav_history:
        return {"error": "No years simulated"}

    final_nav    = nav_history[max(nav_history)]
    total_return = (final_nav / STARTING_CAPITAL - 1) * 100
    n_years      = len(nav_history)
    cagr         = ((final_nav / STARTING_CAPITAL) ** (1 / n_years) - 1) * 100

    ftse_nav = STARTING_CAPITAL
    for yr in BACKTEST_YEARS:
        if yr in nav_history:
            ftse_nav *= (1 + FTSE100_ANNUAL_TR.get(yr, 0))
    ftse_total = (ftse_nav / STARTING_CAPITAL - 1) * 100
    ftse_cagr  = ((ftse_nav / STARTING_CAPITAL) ** (1 / n_years) - 1) * 100

    returns = [(log["end_nav"] / log["start_nav"]) - 1 for log in year_logs]
    avg_ret = sum(returns) / len(returns) if returns else 0
    vol     = math.sqrt(sum((r - avg_ret)**2 for r in returns) / len(returns)) if len(returns) > 1 else 0
    sharpe  = (avg_ret - RF) / vol if vol > 0 else 0

    neg_rets = [r for r in returns if r < 0]
    down_dev = math.sqrt(sum(r**2 for r in neg_rets) / len(neg_rets)) if neg_rets else 0
    sortino  = (avg_ret - RF) / down_dev if down_dev > 0 else 0

    peak, max_dd, running_nav = STARTING_CAPITAL, 0.0, STARTING_CAPITAL
    for log in year_logs:
        running_nav = log["end_nav"]
        if running_nav > peak:
            peak = running_nav
        dd = (peak - running_nav) / peak
        if dd > max_dd:
            max_dd = dd

    return {
        "strategy":           strategy,
        "starting_capital":   STARTING_CAPITAL,
        "final_nav":          round(final_nav, 2),
        "total_return_pct":   round(total_return, 2),
        "cagr_pct":           round(cagr, 2),
        "sharpe":             round(sharpe, 4),
        "sortino":            round(sortino, 4),
        "max_drawdown_pct":   round(max_dd * 100, 2),
        "ann_volatility_pct": round(vol * 100, 2),
        "total_cgt_paid":     round(total_cgt_paid, 2),
        "total_div_tax":      round(total_div_tax, 2),
        "total_gross_divs":   round(total_gross_divs, 2),
        "total_trade_costs":  round(total_costs - total_cgt_paid, 2),
        "years_simulated":    n_years,
        "ftse_final_nav":     round(ftse_nav, 2),
        "ftse_total_return":  round(ftse_total, 2),
        "ftse_cagr":          round(ftse_cagr, 2),
        "year_logs":          year_logs,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  DISPLAY
# ══════════════════════════════════════════════════════════════════════════════

def print_backtest(result):
    if "error" in result:
        print(f"Backtest error: {result['error']}")
        return

    s = result["strategy"].replace("_", " ").title()
    print(f"\n{'='*60}")
    print(f"  ScoreDCS Backtester — {s}")
    print(f"{'='*60}")
    print(f"  Period:              2016–2025 ({result['years_simulated']} years)")
    print(f"  Starting capital:    £{result['starting_capital']:>12,.0f}")
    print(f"  Final NAV:           £{result['final_nav']:>12,.0f}")
    print(f"  Total Return:        {result['total_return_pct']:>+10.2f}%")
    print(f"  CAGR:                {result['cagr_pct']:>+10.2f}%")
    print()
    print(f"  {'── Risk Metrics ──'}")
    print(f"  Sharpe Ratio:        {result['sharpe']:>10.4f}")
    print(f"  Sortino Ratio:       {result['sortino']:>10.4f}")
    print(f"  Max Drawdown:        {result['max_drawdown_pct']:>9.2f}%")
    print(f"  Ann. Volatility:     {result['ann_volatility_pct']:>9.2f}%")
    print()
    print(f"  {'── Benchmark: FTSE 100 (Total Return, calendar year) ──'}")
    print(f"  FTSE 100 Final NAV:  £{result['ftse_final_nav']:>12,.0f}")
    print(f"  FTSE 100 Total Ret:  {result['ftse_total_return']:>+10.2f}%")
    print(f"  FTSE 100 CAGR:       {result['ftse_cagr']:>+10.2f}%")
    print(f"  Alpha (CAGR):        {result['cagr_pct'] - result['ftse_cagr']:>+10.2f}%")
    print(f"  Note: Strategy runs May–Apr; FTSE benchmark is Jan–Dec.")
    print(f"        Year-by-year alpha comparisons are approximate.")
    print()
    print(f"  {'── Tax & Cost Summary ──'}")
    print(f"  Gross Dividends:     £{result['total_gross_divs']:>12,.0f}")
    print(f"  Dividend Tax Paid:   £{result['total_div_tax']:>12,.0f}")
    print(f"  CGT Paid:            £{result['total_cgt_paid']:>12,.0f}")
    print(f"  Trade Costs:         £{result['total_trade_costs']:>12,.0f}")
    print(f"  Total Tax+Costs:     £{result['total_div_tax'] + result['total_cgt_paid'] + result['total_trade_costs']:>12,.0f}")
    print()
    print(f"  {'── Year-by-Year Summary ──'}")
    print(f"  {'Year':<6} {'NAV (£)':>12} {'Strategy':>10} {'FTSE100':>10} {'Alpha':>8} {'CGT (£)':>10} {'Stocks':>7}")
    print(f"  {'-'*70}")
    for log in result["year_logs"]:
        alpha = log["ann_return"] - log["ftse_return"]
        print(f"  {log['year']:<6} {log['end_nav']:>12,.0f}"
              f" {log['ann_return']:>+9.2f}%"
              f" {log['ftse_return']:>+9.2f}%"
              f" {alpha:>+7.2f}%"
              f" {log['cgt_paid']:>10,.0f}"
              f" {log['n_holdings']:>7}")
    print(f"  {'-'*70}")
    print()

    for log in result["year_logs"]:
        yr    = log["year"]
        alpha = log["ann_return"] - log["ftse_return"]
        stops = log.get("stops", [])
        print(f"  {'='*72}")
        print(f"  {yr} Portfolio  (May {yr} → Apr {yr+1})"
              f"   Return: {log['ann_return']:+.2f}%"
              f"   FTSE: {log['ftse_return']:+.2f}%"
              f"   Alpha: {alpha:+.2f}%")
        if stops:
            print(f"  Stop-losses triggered: "
                  + ", ".join(f"{t} ({d}%)" for t, d in stops)
                  + f"  →  £{log['gilt_cash']:,.0f} in gilts")
        print(f"  {'='*72}")
        print(f"  {'Ticker':<10} {'Score':>6} {'Wt%':>5} {'Entry(p)':>9} {'Exit(p)':>9} {'Return':>10} {'End Val(£)':>11}")
        print(f"  {'-'*67}")
        for h in log.get("holdings", []):
            ret_str = h.get("return_str", "N/A")
            sc_str  = f"{h['score']:.1f}"   if h["score"]   is not None else "  N/A"
            ep_str  = f"{h['entry_p']:.0f}" if h["entry_p"] is not None else "    N/A"
            xp_str  = f"{h['exit_p']:.0f}"  if h["exit_p"]  is not None else "STOPPED"
            flag    = " *" if h.get("stopped") else ""
            print(f"  {h['ticker']:<10} {sc_str:>6} {h['weight']:>4.1f}%"
                  f" {ep_str:>9} {xp_str:>9} {ret_str:>10} {h['value_end']:>11,.0f}{flag}")
        print(f"  {'-'*67}")
        print(f"  Gross div: £{log['gross_div']:>9,.0f}   "
              f"Div tax: £{log['div_tax']:>9,.0f}   "
              f"CGT: £{log['cgt_paid']:>9,.0f}   "
              f"Commission: £{log['comm_costs']:>7,.0f}")
        print()


if __name__ == "__main__":
    import sys

    strategies = ["score_weighted", "markowitz"]
    if len(sys.argv) > 1 and sys.argv[1] in strategies:
        strategies = [sys.argv[1]]

    results = {}
    for strat in strategies:
        print(f"\nRunning {strat} backtest...")
        r = run_backtest(strategy=strat, verbose=True)
        results[strat] = r
        print_backtest(r)

    if len(results) == 2:
        sw = results["score_weighted"]
        mz = results["markowitz"]
        print(f"\n{'='*60}")
        print(f"  Head-to-Head Comparison")
        print(f"{'='*60}")
        print(f"  {'Metric':<25} {'Score-Wtd':>12} {'Markowitz':>12} {'FTSE 100':>12}")
        print(f"  {'-'*63}")
        ftse_values = {
            "final_nav":       sw["ftse_final_nav"],
            "cagr_pct":        sw["ftse_cagr"],
            "sharpe":          None,
            "sortino":         None,
            "max_drawdown_pct": None,
        }
        metrics = [
            ("Final NAV (£)",    "final_nav",        "£{:,.0f}"),
            ("CAGR (%)",         "cagr_pct",         "{:+.2f}%"),
            ("Sharpe",           "sharpe",            "{:.4f}"),
            ("Sortino",          "sortino",            "{:.4f}"),
            ("Max Drawdown (%)", "max_drawdown_pct",  "{:.2f}%"),
        ]
        for label, key, fmt in metrics:
            sv  = fmt.format(sw[key])
            mv  = fmt.format(mz[key])
            fv_raw = ftse_values.get(key)
            fv  = fmt.format(fv_raw) if fv_raw is not None else "    N/A"
            print(f"  {label:<25} {sv:>12} {mv:>12} {fv:>12}")
        print()
