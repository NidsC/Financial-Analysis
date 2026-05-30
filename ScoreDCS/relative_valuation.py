import sqlite3
import os

# Path to UKStocksLibrary database — read-only, no API key needed
_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "uk_equity_library.db")

# Cache: sector medians loaded once per session
_sector_medians_cache = None


def _load_sector_medians():
    global _sector_medians_cache
    if _sector_medians_cache is not None:
        return _sector_medians_cache

    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    # Use most recent full year (exclude current partial year)
    import datetime
    current_year = str(datetime.date.today().year)
    cursor = conn.execute("SELECT MAX(year) FROM sector_medians WHERE year < ?", (current_year,))
    latest_year = cursor.fetchone()[0]

    cursor = conn.execute("""
        SELECT sector, median_pe_ratio, median_ev_ebitda, median_price_to_book, median_peg_ratio
        FROM sector_medians
        WHERE year = ?
    """, (latest_year,))
    rows = cursor.fetchall()
    conn.close()

    _sector_medians_cache = {
        row["sector"]: {
            "pe":       row["median_pe_ratio"],
            "ev_ebitda": row["median_ev_ebitda"],
            "pb":       row["median_price_to_book"],
            "peg":      row["median_peg_ratio"],
        }
        for row in rows
    }
    _sector_medians_cache["_year"] = latest_year
    return _sector_medians_cache


def _get_company_data(ticker):
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row

    # Get sector from companies table
    cursor = conn.execute("SELECT sector FROM companies WHERE ticker = ?", (ticker,))
    company = cursor.fetchone()
    if company is None:
        conn.close()
        return None

    sector = company["sector"]

    # Get most recent year's fundamentals
    cursor = conn.execute("""
        SELECT pe_ratio, ev_ebitda, price_to_book, peg_ratio
        FROM fundamentals
        WHERE ticker = ?
        ORDER BY year DESC
        LIMIT 1
    """, (ticker,))
    fund = cursor.fetchone()
    conn.close()

    if fund is None:
        return {"sector": sector, "pe": None, "ev_ebitda": None, "pb": None, "peg": None}

    return {
        "sector":    sector,
        "pe":        fund["pe_ratio"],
        "ev_ebitda": fund["ev_ebitda"],
        "pb":        fund["price_to_book"],
        "peg":       fund["peg_ratio"],
    }


def _score_multiple(stock_val, sector_median):
    """
    Score 0–2: lower multiple = cheaper = higher score (for PE, EV/EBITDA, P/B, PEG).
    Returns 1 (neutral) when data is missing.
    """
    if stock_val is None or stock_val <= 0 or sector_median is None or sector_median == 0:
        return 1
    ratio = stock_val / sector_median
    if ratio <= 0.75:
        return 2   # meaningful discount to sector
    elif ratio <= 1.10:
        return 1   # roughly in line
    else:
        return 0   # premium to sector


def relative_valuation(ticker):
    medians = _load_sector_medians()
    latest_year = medians.get("_year", "N/A")

    stock = _get_company_data(ticker)
    if stock is None:
        return {
            "Sector": "Unknown",
            "P/E": None, "Sector Med P/E": None,
            "EV/EBITDA": None, "Sector Med EV/EBITDA": None,
            "P/B": None, "Sector Med P/B": None,
            "PEG": None, "Sector Med PEG": None,
            "RV Score": 4,  # neutral
            "RV Year": latest_year,
        }

    sector = stock["sector"]
    med = medians.get(sector, {})

    pe       = stock["pe"]
    ev_ebitda = stock["ev_ebitda"]
    pb       = stock["pb"]
    peg      = stock["peg"]

    pe_score  = _score_multiple(pe,        med.get("pe"))
    ev_score  = _score_multiple(ev_ebitda, med.get("ev_ebitda"))
    pb_score  = _score_multiple(pb,        med.get("pb"))
    peg_score = _score_multiple(peg,       med.get("peg"))

    rv_total = pe_score + ev_score + pb_score + peg_score  # max 8

    return {
        "Sector":               sector,
        "P/E":                  round(pe, 2)        if pe        else None,
        "Sector Med P/E":       round(med["pe"], 2) if med.get("pe") else None,
        "EV/EBITDA":            round(ev_ebitda, 2) if ev_ebitda else None,
        "Sector Med EV/EBITDA": round(med["ev_ebitda"], 2) if med.get("ev_ebitda") else None,
        "P/B":                  round(pb, 2)        if pb        else None,
        "Sector Med P/B":       round(med["pb"], 2) if med.get("pb") else None,
        "PEG":                  round(peg, 2)       if peg       else None,
        "Sector Med PEG":       round(med["peg"], 2) if med.get("peg") else None,
        "RV Score":             rv_total,
        "RV Year":              latest_year,
    }
