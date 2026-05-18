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
Dividend Growth Rate and FCF Yield, giving investors a quick side-by-side view of dividend stock quality. The
script is intentionally flexible: any metric available through yfinance can be added or removed from the output table
with minimal effort, making it a practical starting point for anyone building their own stock screening workflow.


V2DCS.py
V2 — Robustness & Error Handling
This iteration focused on making the data retrieval layer resilient to the inconsistencies and gaps common in yfinance
data. A clean() helper function was introduced to safely extract rows from financial statement DataFrames, returning
None instead of crashing when a row label is missing or unavailable for a given ticker. All arithmetic operations in the
output table are now guarded against None values, and the main data loop wraps each ticker in a try/except block so
that a single failed ticker is skipped with a warning rather than halting the entire run.

ScoreDCS — Dividend Stock Scoring Tool
  A Python script that scores and compares dividend stocks across the London Stock Exchange (LSE), generating BUY / KEEP /
   SELL signals based on fundamental financial analysis.

  How It Works
  Stocks are evaluated across three pillars, each contributing to a total score out of 30 (displayed as a percentage)
  There are 3 pillars accessed here:
  1. Dividend Quality - Free Cash Flow Yield, Payout Ratio, Dividend Growth Rate (DGR)
  2. Financial Stability - Debt/EBITDA Leverage Ratio, EBIT Interest Coverage
     It simply looks at a company's ability to cover long term and short term payments
  3. Capital Efficiency - Return on Equity (ROE), Return on Invested Capital (ROIC)

  Signal Thresholds
  BUY - ≥ 19 / 30
  KEEP - ≥ 12 / 30
  SELL - < 12 / 30

  Output Columns
  Ticker, Price, Div% Yield, FCF Yield, Payout Ratio, DGR%, Score1 (Dividend Quality), Leverage Ratio, Coverage,
  Score2 (Financial Stability), ROE, ROIC, Score3 (Capital Efficiency), Total Score (%), Signal

  Dependencies
  yfinance
  pandas

  Install with:
  pip install yfinance pandas
  
  Usage
  Clone the file and open the ScoreDCS in PyCharm or Spyder
  Edit the tickers list in the script to include your desired LSE stock tickers (e.g. "HSBA.L", "BP.L"), then run.
  OR
  Run the following command in terminal.
  python ScoreDCS.py
  
  Note: Data is pulled live from Yahoo Finance via yfinance. Missing or unavailable data for a metric defaults to a 
  neutral mid-range score rather than failing the stock entirely.

  What it should look like: 
  <img width="1240" height="819" alt="image" src="https://github.com/user-attachments/assets/39937ad8-934f-45d5-8f1f-cbbcc4b9dfb1" />
  All the companies in the table has a market capitalisation higher than GBP 2 billion and have a dividend yield higher than 4%. 


  Unilever 3 Statement Financial Model - Excel 
  To download the excel file, click on the file link or click on file on repository main page which takes you to the Files viewing page. Click on 'View Raw' to download. 
  Further details given inside the Excel file. 



