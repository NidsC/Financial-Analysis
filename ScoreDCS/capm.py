# CAPM - Capital Asset Pricing Model
# An attempt to compare the true dividend yield with the expected returns
# It is an estimation of whether the investor is properly rewarded for the risk he takes

# Note that the Equation of CAPM is E(r) = Rf + Beta * (Rm - Rf)
# Rm value used will be 9% since the long run total returns for FTSE 250 including dividends is 8.5-9.5%
# Rf value used will be 4.4$ since the BoE has established the current UK 10 yr Gilt yield to be approximately 4.4% as of may 2026


import yfinance as yf

def comp(E_r, divyield):
    if E_r is None or divyield is None:
        return "Insufficient Data"
    diff = divyield - E_r
    if diff > 1:
        return "Over"
    elif diff < -1:
        return "Under"
    else:
        return "Fairly"

def capm(ticker):
    stock = yf.Ticker(ticker)
    info = stock.info

    beta = info.get("beta")
    rm = 0.09
    rf = 0.044
    E_r = round((rf + beta * (rm - rf)) * 100, 4) if beta else None
    divyield = info.get("dividendYield")

    return {"Expected Return": E_r,
            "dividend yield": divyield,
            "Compensated?": comp(E_r, divyield)
            }

