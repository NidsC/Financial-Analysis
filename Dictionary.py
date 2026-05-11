import yfinance as yf

stock = yf.Ticker("BP.L")
print("Information")
print(stock.info.keys())
print("Financial Data")
print(stock.financials.index.tolist())
print("Cashflow Data")
print(stock.cashflow.index.tolist())
print("Balance Sheet Data")
print(stock.balance_sheet.index.tolist())
