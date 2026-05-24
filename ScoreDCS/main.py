# ScoreDCS is now a modular file, connected with several other files. Read the README.md to better understand
# Import the pandas, yfinance and numpy as we will use them
import yfinance as yf
import pandas as pd
# import numpy as np

from universe import tickers
from utils import clean, signal
from calculator import get_data
from dupontcalc import dupont
from capm import capm

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
        data.append(row)
    except Exception as e:
        import traceback
        print(f"Skipping {t}: {e}")
        traceback.print_exc()

df = pd.DataFrame(data)
print(df)
