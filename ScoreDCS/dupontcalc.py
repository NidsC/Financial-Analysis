import sqlite3
import os

_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "uk_equity_library.db")


def roe_driver(npm, a_turn, eq_multi):
    if npm is None or a_turn is None or eq_multi is None:
        return "Insufficient Data"
    scores = {
        "NPM":      npm / 0.1,
        "Turnover": a_turn / 1,
        "Leverage": eq_multi / 2,
    }
    return max(scores, key=scores.get)


def dupont(ticker):
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row

    # Most recent year's financials
    rows = conn.execute("""
        SELECT net_income, revenue, total_assets, total_equity
        FROM financials
        WHERE ticker = ?
        ORDER BY year DESC LIMIT 2
    """, (ticker,)).fetchall()
    conn.close()

    if not rows:
        return {
            "Net Profit Margin": None,
            "Asset Turnover":    None,
            "Equity Multiplier": None,
            "ROE Driver":        "Insufficient Data",
            "Calculated ROE":    None,
        }

    r = rows[0]
    net_income  = r["net_income"]
    revenue     = r["revenue"]
    total_assets = r["total_assets"]

    # Average equity over two most recent years if available
    eq1 = rows[0]["total_equity"]
    eq2 = rows[1]["total_equity"] if len(rows) > 1 else None
    t_equity = (eq1 + eq2) / 2 if eq1 and eq2 else eq1

    npm     = round(net_income / revenue, 4)     if net_income and revenue and revenue != 0   else None
    a_turn  = round(revenue / total_assets, 4)   if revenue and total_assets and total_assets != 0 else None
    eq_multi = round(total_assets / t_equity, 4) if t_equity and total_assets and t_equity != 0   else None

    calc_roe = npm * a_turn * eq_multi if npm and a_turn and eq_multi else None

    return {
        "Net Profit Margin": npm,
        "Asset Turnover":    a_turn,
        "Equity Multiplier": eq_multi,
        "ROE Driver":        roe_driver(npm, a_turn, eq_multi),
        "Calculated ROE":    round(calc_roe, 4) if calc_roe else None,
    }
