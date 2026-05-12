# An application tool that scores the dividend stocks for comparison and provides a buy, keep or sell signal
# There are 3 pillars to the socring system
# 1) Dividend Quality which analyses the dividend yield and the growth rate of dividends
# 2) Financial Stability which analyses the strength of a companys business model and its ability to cover debts and interest expenses
# 3) Capital Efficiency which looks at the returns on equity and the returns on invested capital

# This python script will do both, the calculation for the relevant metrics prints a score for each pillar.

# Import the pandas, yfinance and numpy as we will use them
import yfinance as yf
import pandas as pd
# import numpy as np

# adjust the sizing constraint for the dataframe table
pd.set_option("display.max_columns", None)
pd.set_option("display.width", None)
pd.set_option("display.max_colwidth", None)

# clean the data in case the yfinance data source returns invalid values
def clean(df, row):
    try:
        return df.loc[row].iloc[0]
    except (KeyError, IndexError):
        return None

# define your tickers, the process of making an interactive UI to add and remove stocks will come later. For now it will have to be done manually
# tickers = ["BP.L", "IAG.L", "CNA.L", "NG.L", "ITM.L"]
# tickers = ["BP.L", "IAG.L", "CNA.L", "NG.L", "ITM.L", "VOD.L", "ITV.L", "HLN.L", "BYIT.L", "BLND.L", "AV.L", "LGEN.L", "RWS.L", "NCC.L"]
tickers = ["HSBA.L", "BATS.L", "ULVR.L", "BP.L", "NWG.L", "DGE.L", "RKT.L", "IMB.L", "AV.L", "LGEN.L", "ADM.L", "SGRO.L", "SDLF.L", "MNG.L", "SBRY.L", "ICG.L", "HBR.L", "INVP.L", "IGG.L", "KGF.L", "ITH.L", "LMP.L", "LAND.L", "BBOX.L", "ABDN.L", "N91.L", "WTB.L", "BLND.L", "BTRW.L", "PSN.L", "HIK.L", "EMG.L", "ITV.L", "WPP.L", "TW.L", "TBCG.L", "PNN.L", "UTG.L", "PHP.L", "INPP.L", "HICL.L", "TCAP.L", "UKW.L", "RAT.L"]

def signal(Tscore):
    if Tscore >= 19:
        return "BUY"
    elif Tscore >= 12:
        return "KEEP"
    else:
        return "SELL"

def get_data(ticker):
    stock = yf.Ticker(ticker)
    info = stock.info
    financial = stock.financials
    dividends = stock.dividends
    balance_sheet = stock.balance_sheet
    cashflow = stock.cashflow


    fcf = clean(cashflow, "Free Cash Flow")
    fcfyield = round(fcf / info.get("marketCap"), 2) if fcf and info.get("marketCap") else None
    if fcfyield is None:
        fcfpoint = 2
    elif fcfyield >= 0.08:
        fcfpoint = 4
    elif fcfyield >=0.05:
        fcfpoint = 3
    elif fcfyield >= 0.02:
        fcfpoint = 2
    elif fcfyield > 0:
        fcfpoint = 1
    elif fcfyield <= 0:
        fcfpoint = 0

    payout = info.get("payoutRatio")
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
    elif payout <= 0.1:
        paypoint = 1

    annual_div = dividends.resample("YE").sum()
    last_5 = annual_div.tail(6)
    valid = last_5.dropna()
    valid = valid[valid > 0]
    if len(valid) >= 2:
        yoy_changes = valid.pct_change().dropna()
        dgr = yoy_changes.mean()
    else:
        dgr = None

    if dgr is None:
        dgrpoint = 1
    elif dgr >= 6:
        dgrpoint = 4
    elif dgr >= 4:
        dgrpoint = 3
    elif dgr >= 2:
        dgrpoint = 2
    elif dgr >= 0:
        dgrpoint = 1
    elif dgr < 0:
        dgrpoint = 0

    debt = clean(balance_sheet, "Total Debt")
    ebitda = info.get("ebitda")
    leverage = None
    levpoint = 0

    if debt is None or ebitda is None:
        levpoint = 2
    elif debt <= 0:
        levpoint = 5
    elif ebitda <= 0:
        levpoint = 0
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

    ebit = clean(financial, "EBIT")
    interest = clean(financial, "Interest Expense")
    coverage = None

    if ebit is None or interest is None:
        coverpoint = 2
    elif ebit <= 0:
        coverpoint = 0
    elif interest <= 0:
        coverpoint = 4
    else:
        coverage = ebit / interest
        if coverage >= 10:
            coverpoint = 4
        elif coverage >= 5:
            coverpoint = 3
        elif coverage >= 2.5:
            coverpoint = 2
        elif coverage >= 1.5:
            coverpoint = 1
        else:
            coverpoint = 0

    roe = info.get("returnOnEquity")

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
    elif roe < 0:
        roepoint = 0

    invcap = clean(balance_sheet, "Invested Capital")
    tax = 0.21 if ".L" not in ticker else 0.25

    if ebit is None or invcap is None:
        roicpoint = 2
        roic = None
    else:
        NOPAT = ebit * (1 - tax)
        roic = NOPAT / invcap
        if roic >= 0.2:
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


    return {"Ticker": ticker,
            "Price": info.get("currentPrice"),
            "Div%Yield": info.get("dividendYield"),
            "FCF Yield": round(fcfyield, 2) if fcfyield else None,
            "payout": round(payout, 2) if payout else None,
            "DGR%": round(dgr, 2) if dgr is not None else None,
            "Score1": dgrpoint + fcfpoint + paypoint,
            "Leverage Ratio": round(leverage, 2) if leverage is not None else None,
            "Coverage": round(coverage, 2) if coverage is not None else None,
            "Score2": levpoint + coverpoint,
            "ROE": round(roe, 2) if roe else None,
            "ROIC": round(roic, 2) if roic else None,
            "Score3": roepoint + roicpoint,
            "Total Score": round((Tscore / 30) * 100, 2),
            "Signal": signal(Tscore),
            }

data = []
for t in tickers:
    try:
        data.append(get_data(t))
    except Exception as e:
        import traceback
        print(f"Skipping {t}: {e}")
        traceback.print_exc()

df = pd.DataFrame(data)

print(df)
