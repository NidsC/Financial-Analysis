import sqlite3
import os

_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "uk_equity_library.db")


def comp(E_r, divyield):
    if E_r is None or divyield is None:
        return "Insufficient Data"
    diff = divyield - E_r
    if diff > 1.0:
        return "Over"
    elif diff < -1.0:
        return "Under"
    else:
        return "Fairly"


def capm(ticker):
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row

    company = conn.execute("SELECT beta FROM companies WHERE ticker = ?", (ticker,)).fetchone()
    fund = conn.execute("""
        SELECT dividend_yield FROM fundamentals
        WHERE ticker = ? ORDER BY year DESC LIMIT 1
    """, (ticker,)).fetchone()
    conn.close()

    beta = company["beta"] if company else None
    divyield = fund["dividend_yield"] if fund else None

    rm = 0.09
    rf = 0.044
    E_r = round((rf + beta * (rm - rf)) * 100, 4) if beta else None
    divyield_pct = round(divyield * 100, 4) if divyield else None

    return {
        "Beta":                round(beta, 4) if beta else None,
        "Expected Return (%)": E_r,
        "Div Yield (%)":       divyield_pct,
        "Compensated?":        comp(E_r, divyield_pct),
    }
