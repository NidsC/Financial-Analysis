# Dividend Stock Comparison Tool, branch variant of SCC.py
# The Goal is to identify the best stocks

# import the following - standard
import yfinance as yf
import pandas as pd
import numpy as np

pd.set_option("display.max_columns", None)
pd.set_option("display.width", None)
pd.set_option("display.max_colwidth", None)

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
    ebit = financial.loc["EBIT"].iloc[0]
    interest = financial.loc["Interest Expense"].iloc[0]
    total_debt = balance_sheet.loc["Total Debt"].iloc[0]
    equity = balance_sheet.loc["Stockholders Equity"].iloc[0]
    cash = balance_sheet.loc["Cash And Cash Equivalents"].iloc[0]
    invcap = balance_sheet.loc["Invested Capital"].iloc[0]
    fcf = cashflow.loc["Free Cash Flow"].iloc[0]

    # you can add and remove lines here according to what stats you want to see
    return {"Ticker": ticker,
            "Price": info.get("currentPrice"),
            "MCap(MNs)": int(round(info.get("marketCap") / 1e6)),
            "Rev(MNs)": int(round(info.get("totalRevenue") / 1e6)),
            "Payout%": round(payout, 2) * 100,
#            "EBITDA": int(round(info.get("ebitda")/ 1e6)),
            "ROE": info.get("returnOnEquity"),
#            "Debt": round(info.get("totalDebt") / 1e6, 2),
            "Debt/EBITDA": round((info.get("totalDebt") / 1e6) / (info.get("ebitda")/ 1e6), 2),
            "Interest(MNs)": round(interest / 1e6, 2),
            "Coverage": round( ebit / interest, 2),
            "DGR %": round(growth_rate * 100, 2) if growth_rate else None,
            "ROIC":  round((total_debt + equity - cash) / invcap, 2),
            "FCF Yield": round( fcf / info.get("marketCap"), 2),
            "Beta": info.get("beta")
            }

#            "P/E": round(float(trailpe, 2) if info.get("trailingPE") else None,
#            "EPS": info.get("trailingEps"),

data = [get_data(t) for t in tickers]

df = pd.DataFrame(data)

print(df)
