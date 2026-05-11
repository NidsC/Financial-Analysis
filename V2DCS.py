# Iteration of DCS.py
# Goal - To reduce the crashing issue and avoid situations where data returned as None
# results in error

# import the following - standard
import yfinance as yf
import pandas as pd
import numpy as np

pd.set_option("display.max_columns", None)
pd.set_option("display.width", None)
pd.set_option("display.max_colwidth", None)

def clean(df, row):
    try:
        return df.loc[row].iloc[0]
    except (KeyError, IndexError):
        return None

# define your tickers, the process of making an interactive UI to add and remove stocks will come later. For now it will have to be done manually
tickers = ["BP.L", "IAG.L", "CNA.L", "NG.L", "ITM.L", "VOD.L", "ITV.L", "HLN.L", "BYIT.L", "BLND.L", "AV.L", "LGEN.L", "RWS.L", "NCC.L"]

# now, define the function to draw the data from yfinance
def get_data(ticker):
    stock = yf.Ticker(ticker)
    info = stock.info
    financial = stock.financials
    dividends = stock.dividends
    balance_sheet = stock.balance_sheet
    cashflow = stock.cashflow

    growth_rate = None

    annual_div = dividends.resample("YE").sum()
    last_3 = annual_div.tail(3)
    if len(last_3) >= 3:
        start = last_3.iloc[0]
        end = last_3.iloc[-1]

        if start and not np.isnan(start):
            growth_rate = (end / start) ** (1 / 3) - 1

    #    trailpe = info.get("trailingPE") # the data taken from yfinance for PE ratios are often infinity or none, hence we adjust by using a float and an 'else None'
    # this step will have to be repeated for any values where you might get none numerical values
    payout = info.get("payoutRatio")
    ebit = clean(financial, "EBIT")
    interest = clean(financial, "Interest Expense")
    total_debt = clean(balance_sheet, "Total Debt")
    equity = clean(balance_sheet, "Stockholders Equity")
    cash = clean(balance_sheet, "Cash And Cash Equivalents")
    invcap = clean(balance_sheet, "Invested Capital")
    fcf = clean(cashflow, "Free Cash Flow")

    # you can add and remove lines here according to what stats you want to see
    return {"Ticker": ticker,
            "Price": info.get("currentPrice"),
            "MCap(MNs)": int(round(info.get("marketCap") / 1e6)) if info.get("marketCap") else None,
            "Rev(MNs)": int(round(info.get("totalRevenue") / 1e6)) if info.get("totalRevenue") else None,
            "Payout%": round(payout, 2) * 100 if payout else None,
            "EBITDA": int(round(info.get("ebitda")/ 1e6)) if info.get("ebitda") else None,
            "ROE": info.get("returnOnEquity"),
            "Debt": round(total_debt / 1e6, 2) if total_debt else None,
            "Debt/EBITDA": round((total_debt / 1e6) / (info.get("ebitda")/ 1e6), 2) if total_debt and info.get("ebitda") else None,
            "Interest(MNs)": round(interest / 1e6, 2) if interest else None,
            "Coverage": round( ebit / interest, 2) if ebit and interest else None,
            "DGR %": round(growth_rate * 100, 2) if growth_rate else None,
            "FCF Yield": round( fcf / info.get("marketCap"), 2) if fcf and info.get("marketCap") else None,
            "Beta": info.get("beta")
            }

#            "P/E": round(float(trailpe, 2) if info.get("trailingPE") else None,
#            "EPS": info.get("trailingEps"),

data = []
for t in tickers:
    try:
        data.append(get_data(t))
    except Exception as e:
        print(f"Skipping {t}: {e}")

df = pd.DataFrame(data)

print(df)

