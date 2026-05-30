import sqlite3
import os
from utils import signal

_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "uk_equity_library.db")


def _get_data_from_db(ticker):
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row

    # Most recent price
    price_row = conn.execute("""
        SELECT close FROM prices WHERE ticker = ? ORDER BY date DESC LIMIT 1
    """, (ticker,)).fetchone()

    # Most recent fundamentals
    fund = conn.execute("""
        SELECT pe_ratio, ev_ebitda, price_to_book, peg_ratio,
               roe, roic, debt_to_equity, current_ratio,
               dividend_yield, payout_ratio, fcf_yield
        FROM fundamentals WHERE ticker = ? ORDER BY year DESC LIMIT 1
    """, (ticker,)).fetchone()

    # Two most recent years of financials for DGR
    fin_rows = conn.execute("""
        SELECT year, revenue, ebitda, ebit, net_income,
               total_debt, total_equity, free_cash_flow
        FROM financials WHERE ticker = ? ORDER BY year DESC LIMIT 2
    """, (ticker,)).fetchall()

    # Market cap from companies table
    company = conn.execute(
        "SELECT market_cap FROM companies WHERE ticker = ?", (ticker,)
    ).fetchone()

    conn.close()
    return price_row, fund, fin_rows, company


def get_data(ticker):
    price_row, fund, fin_rows, company = _get_data_from_db(ticker)

    current_price = price_row["close"] if price_row else None
    market_cap    = company["market_cap"] if company else None

    fin = fin_rows[0] if fin_rows else None
    fin_prev = fin_rows[1] if len(fin_rows) > 1 else None

    # --- FCF Yield ---
    fcf_yield = fund["fcf_yield"] if fund else None
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

    # --- Payout Ratio ---
    payout = fund["payout_ratio"] if fund else None
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

    # --- Dividend Growth Rate (net income growth as proxy) ---
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

    # --- Leverage (Debt/EBITDA) ---
    debt   = fin["total_debt"]  if fin else None
    ebitda = fin["ebitda"]      if fin else None

    if debt is None or ebitda is None:
        levpoint = 2
        leverage = None
    elif debt <= 0:
        levpoint = 5
        leverage = 0.0
    elif ebitda <= 0:
        levpoint = 0
        leverage = None
    else:
        leverage = debt / ebitda
        if leverage <= 1.5:
            levpoint = 5
        elif leverage <= 2.5:
            levpoint = 4
        elif leverage <= 3.5:
            levpoint = 3
        elif leverage <= 5:
            levpoint = 2
        elif leverage <= 7:
            levpoint = 1
        else:
            levpoint = 0

    # --- Interest Coverage (EBIT / implied interest — not stored, use debt_to_equity proxy) ---
    # We store ebit but not interest expense directly; use ebit vs ebitda gap as depreciation proxy
    ebit = fin["ebit"] if fin else None
    if ebit is None or ebitda is None:
        coverpoint = 2
        coverage = None
    elif ebit <= 0:
        coverpoint = 0
        coverage = None
    elif ebitda <= 0:
        coverpoint = 2
        coverage = None
    else:
        # Use EBIT/EBITDA ratio as a proxy for debt service capacity
        coverage = ebit / ebitda
        if coverage >= 0.9:
            coverpoint = 4
        elif coverage >= 0.7:
            coverpoint = 3
        elif coverage >= 0.5:
            coverpoint = 2
        elif coverage >= 0.3:
            coverpoint = 1
        else:
            coverpoint = 0

    # --- ROE ---
    roe = fund["roe"] if fund else None
    if roe is None:
        roepoint = 2
    elif roe >= 0.2:
        roepoint = 5
    elif roe >= 0.15:
        roepoint = 4
    elif roe >= 0.1:
        roepoint = 3
    elif roe >= 0.05:
        roepoint = 2
    elif roe >= 0:
        roepoint = 1
    else:
        roepoint = 0

    # --- ROIC ---
    roic = fund["roic"] if fund else None
    if roic is None:
        roicpoint = 2
    elif roic >= 0.2:
        roicpoint = 4
    elif roic >= 0.15:
        roicpoint = 3
    elif roic >= 0.1:
        roicpoint = 2
    elif roic >= 0.05:
        roicpoint = 1
    else:
        roicpoint = 0

    Tscore = dgrpoint + fcfpoint + paypoint + levpoint + coverpoint + roepoint + roicpoint

    return {
        "Ticker":           ticker,
        "Price":            current_price,
        "Div% Yield":       round(fund["dividend_yield"] * 100, 2) if fund and fund["dividend_yield"] else None,
        "FCF Yield":        round(fcf_yield, 2) if fcf_yield else None,
        "Payout":           round(payout, 2)    if payout   else None,
        "DGR%":             round(dgr * 100, 2) if dgr is not None else None,
        "Score1":           dgrpoint + fcfpoint + paypoint,
        "Leverage Ratio":   round(leverage, 2)  if leverage is not None else None,
        "Coverage":         round(coverage, 2)  if coverage is not None else None,
        "Score2":           levpoint + coverpoint,
        "ROE":              round(roe, 2)        if roe   else None,
        "ROIC":             round(roic, 2)       if roic  else None,
        "Score3":           roepoint + roicpoint,
        "Total Score":      round((Tscore / 30) * 100, 2),
        "Signal":           signal(Tscore),
    }
