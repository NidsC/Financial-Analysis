# Financial-Analysis-and-Modelling
A portfolio of Financial Analysis and Financial Modelling projects! 


Dictionary.py 
A dictionary of attributes and fields for all of the variables from yfinance. 
Press run to see full list

DSC.py
Dividend Stock Comparison Tool is a Python-based financial analysis script that fetches real-time stock data for a 
user-defined list of tickers using the yfinance library. It retrieves key financial metrics — including dividends,
income statements, balance sheets, and cash flow statements — and consolidates them into a clean comparison table. The
tool calculates a range of fundamental ratios such as Payout Ratio, Return on Equity, Debt/EBITDA, Interest Coverage,
Dividend Growth Rate, ROIC, and FCF Yield, giving investors a quick side-by-side view of dividend stock quality. The
script is intentionally flexible: any metric available through yfinance can be added or removed from the output table
with minimal effort, making it a practical starting point for anyone building their own stock screening workflow.


V2DCS.py
V2 — Robustness & Error Handling
This iteration focused on making the data retrieval layer resilient to the inconsistencies and gaps common in yfinance
data. A clean() helper function was introduced to safely extract rows from financial statement DataFrames, returning
None instead of crashing when a row label is missing or unavailable for a given ticker. All arithmetic operations in the
output table are now guarded against None values, and the main data loop wraps each ticker in a try/except block so
that a single failed ticker is skipped with a warning rather than halting the entire run.
