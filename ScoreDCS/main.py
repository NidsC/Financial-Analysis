# ScoreDCS is now a modular file, connected with several other files. Read the README.md to better understand
# Import the pandas, yfinance and numpy as we will use them
import pandas as pd
# import numpy as np

from universe import tickers
from utils import clean, signal
from calculator import get_data
from dupontcalc import dupont
from capm import capm
from relative_valuation import relative_valuation
from dcf import print_dcf
from score_weighted import score_weighted, print_score_weighted
from markowitz import markowitz, print_markowitz

# adjust the sizing constraint for the dataframe table
pd.set_option("display.max_columns", None)
pd.set_option("display.width", None)
pd.set_option("display.max_colwidth", None)

data = []
for t in tickers:
    try:
        row = get_data(t)
        row.update(dupont(t))
        row.update(capm(t))
        row.update(relative_valuation(t))
        data.append(row)
    except Exception as e:
        import traceback
        print(f"Skipping {t}: {e}")
        traceback.print_exc()

df = pd.DataFrame(data)
print(df)

print("\n" + "=" * 55)
print("  DCF VALUATIONS")
print("=" * 55)
for t in tickers:
    print_dcf(t)

# --- Portfolio Optimisation ---
scored_tickers = [(row["Ticker"], row["Total Score"]) for row in data]

print("\n" + "=" * 55)
print("  PORTFOLIO OPTIMISATION — SCORE-WEIGHTED")
print("=" * 55)
sw_result = score_weighted(scored_tickers)
print_score_weighted(sw_result)

print("\n" + "=" * 55)
print("  PORTFOLIO OPTIMISATION — MARKOWITZ MAX-SHARPE")
print("=" * 55)
eligible_tickers = [t for t, s in scored_tickers if s is not None and s >= 67.0]
print(f"Running Markowitz on {len(eligible_tickers)} eligible stocks...")
mz_result = markowitz(eligible_tickers)
print_markowitz(mz_result)
