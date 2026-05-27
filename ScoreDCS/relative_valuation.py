import yfinance as yf
import statistics
from universe import tickers


def _fetch_multiples(ticker):
    info = yf.Ticker(ticker).info
    sector = info.get("sector", "Unknown")
    pe = info.get("trailingPE")
    ev_ebitda = info.get("enterpriseToEbitda")
    pb = info.get("priceToBook")
    peg = info.get("trailingPegRatio")
    return {
        "ticker": ticker,
        "sector": sector,
        "pe": pe,
        "ev_ebitda": ev_ebitda,
        "pb": pb,
        "peg": peg,
    }


def _sector_medians(all_data):
    """Group all_data by sector and return median for each multiple."""
    by_sector = {}
    for row in all_data:
        s = row["sector"]
        by_sector.setdefault(s, {"pe": [], "ev_ebitda": [], "pb": [], "peg": []})
        for m in ("pe", "ev_ebitda", "pb", "peg"):
            if row[m] is not None and row[m] > 0:
                by_sector[s][m].append(row[m])

    medians = {}
    for s, vals in by_sector.items():
        medians[s] = {}
        for m in ("pe", "ev_ebitda", "pb", "peg"):
            lst = vals[m]
            medians[s][m] = statistics.median(lst) if len(lst) >= 2 else None
    return medians


def _score_multiple(stock_val, sector_median):
    """
    Score 0–2 based on how stock multiple compares to sector median.
    Lower multiple = cheaper = higher score (for PE, EV/EBITDA, PB, PEG).
    """
    if stock_val is None or sector_median is None or sector_median == 0:
        return 1  # neutral if data missing
    ratio = stock_val / sector_median
    if ratio <= 0.75:
        return 2   # trading at meaningful discount
    elif ratio <= 1.10:
        return 1   # roughly in line
    else:
        return 0   # premium to sector


# Pre-compute sector medians once across full universe at module import time
_universe_data = None
_medians_cache = None


def _ensure_cache():
    global _universe_data, _medians_cache
    if _medians_cache is None:
        _universe_data = [_fetch_multiples(t) for t in tickers]
        _medians_cache = _sector_medians(_universe_data)


def relative_valuation(ticker):
    _ensure_cache()

    # Find this ticker's data from cached universe fetch
    stock_data = next((d for d in _universe_data if d["ticker"] == ticker), None)
    if stock_data is None:
        stock_data = _fetch_multiples(ticker)

    sector = stock_data["sector"]
    med = _medians_cache.get(sector, {})

    pe = stock_data["pe"]
    ev_ebitda = stock_data["ev_ebitda"]
    pb = stock_data["pb"]
    peg = stock_data["peg"]

    pe_score = _score_multiple(pe, med.get("pe"))
    ev_score = _score_multiple(ev_ebitda, med.get("ev_ebitda"))
    pb_score = _score_multiple(pb, med.get("pb"))
    peg_score = _score_multiple(peg, med.get("peg"))

    rv_total = pe_score + ev_score + pb_score + peg_score  # max 8

    return {
        "Sector": sector,
        "P/E": round(pe, 2) if pe else None,
        "Sector Med P/E": round(med.get("pe"), 2) if med.get("pe") else None,
        "EV/EBITDA": round(ev_ebitda, 2) if ev_ebitda else None,
        "Sector Med EV/EBITDA": round(med.get("ev_ebitda"), 2) if med.get("ev_ebitda") else None,
        "P/B": round(pb, 2) if pb else None,
        "Sector Med P/B": round(med.get("pb"), 2) if med.get("pb") else None,
        "PEG": round(peg, 2) if peg else None,
        "Sector Med PEG": round(med.get("peg"), 2) if med.get("peg") else None,
        "RV Score": rv_total,
    }
