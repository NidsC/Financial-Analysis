
import yfinance as yf

def roe_driver(npm, a_turn, eq_multi):
    if npm is None or a_turn is None or eq_multi is None:
        return "Insufficient Data"

    npm_score = npm / 0.1
    a_turn_score = a_turn / 1
    eq_multi_score = eq_multi / 2

    scores = {
        "NPM": npm_score,
        "Turnover": a_turn_score,
        "Leverage": eq_multi_score
    }
    return max(scores, key=scores.get)


def dupont(ticker):
    stock = yf.Ticker(ticker)
    financial = stock.financials
    balance_sheet = stock.balance_sheet

    netinc = financial.loc["Net Income Common Stockholders"].iloc[0] if "Net Income Common Stockholders" in financial.index else None
    rev = financial.loc["Total Revenue"].iloc[0] if "Total Revenue" in financial.index else None
    t_assets = balance_sheet.loc["Total Assets"].iloc[0] if "Total Assets" in balance_sheet.index else None
    eq1 = balance_sheet.loc["Stockholders Equity"].iloc[0] if "Stockholders Equity" in balance_sheet.index else None
    eq2 = balance_sheet.loc["Stockholders Equity"].iloc[1] if "Stockholders Equity" in balance_sheet.index else None
    t_equity = (eq1 + eq2) / 2 if eq1 and eq2 else eq1

    npm = round(netinc / rev, 4) if netinc and rev else None
    a_turn = round(rev / t_assets, 4) if t_assets and rev else None
    eq_multi = round(t_assets / t_equity, 4) if t_equity and t_assets else None

    calc_roe = npm * a_turn * eq_multi

    return {"Net Profit Margin": npm,
            "Asset Turnover": a_turn,
            "Equity Multiplier": eq_multi,
            "ROE Driver": roe_driver(npm, a_turn, eq_multi),
            "Calculated ROE": calc_roe if calc_roe else None,
            }

# If ROE Driver is:
# NPM, that means company retains a large potion of its earnings, this is good and usually sustainable, it suggests pricing power, strong brand or
# an excellent business model and/or management. E.g. luxury goods, pharmaceuticals or software
# Asset Turnover, that ROE is driven by volume and operational efficiency rather than fat margins. Not a bad thing but not great either
# common in retail, distribution and consumer staple businesses
# Leverage, that ROE is driven by debt borrowing - the comapny is using debt to increase returns to shareholders. The ROE may look good on paper
# but this a big red flag as it is unsustainable and can reduce earnings in future years. Compare with Coverage Ratio to understand more


