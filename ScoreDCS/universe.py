import sqlite3
import os

_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "uk_equity_library.db")

# Screening parameters
MIN_YEARS_YIELD   = 5      # minimum years of dividend yield history required
AVG_YIELD_MIN     = 0.04   # 5-year average dividend yield >= 4%
MAX_YIELD_PER_YR  = 0.25   # cap per-year yield at 25% to exclude special dividend artefacts
TARGET_YEAR       = "2025" # must have fundamentals data for this year


def get_universe(target_year=TARGET_YEAR):
    """
    Return tickers that meet all three criteria:
      1. 5-year average dividend yield >= 4% (capped at 25% per year)
      2. At least 5 years of dividend yield history
      3. Has fundamentals data for target_year
    """
    conn = sqlite3.connect(_DB_PATH)

    rows = conn.execute("""
        SELECT f.ticker
        FROM fundamentals f
        JOIN companies c ON f.ticker = c.ticker
        WHERE f.dividend_yield IS NOT NULL
          AND f.dividend_yield > 0
          AND f.dividend_yield <= ?
        GROUP BY f.ticker
        HAVING COUNT(f.year) >= ?
           AND AVG(f.dividend_yield) >= ?
           AND SUM(CASE WHEN f.year = ? THEN 1 ELSE 0 END) > 0
        ORDER BY AVG(f.dividend_yield) DESC
    """, (MAX_YIELD_PER_YR, MIN_YEARS_YIELD, AVG_YIELD_MIN, target_year)).fetchall()

    conn.close()
    return [r[0] for r in rows]


# Module-level tickers — loaded once on import
tickers = get_universe()

if __name__ == "__main__":
    print(f"Universe ({TARGET_YEAR}, 5yr avg div yield >= 4%): {len(tickers)} companies")
    for t in tickers[:20]:
        print(f"  {t}")
    if len(tickers) > 20:
        print(f"  ... and {len(tickers) - 20} more")
