# ScoreDCS Upgrade & Backtest Plan — 2–3 Days

---

## Backtest Design Decisions — Locked

**Universe:** FTSE 100 + FTSE 250 present-day constituents. Survivorship bias acknowledged explicitly in README — companies that were delisted, went bust, or fell out of the index between 2019–2024 are not included, which means returns will be slightly overstated.

**Dividend screen:** Dividend yield ≥4% at the start of each year using historical data, not current yield.

**Scoring:** ScoreDCS run on each stock that passes the dividend screen, using that year's financial data from FMP.

**Allocation — score-weighted with tiered position sizing based on number of stocks passing the screen:**
- 10 or more stocks pass: maximum 5% per stock
- 5 to 9 stocks pass: maximum 3% per stock, remainder in gilts
- Fewer than 5 stocks pass: 0% deployed, entire portfolio in gilts for that year

**Cash treatment:** Uninvested cash earns the prevailing 1-year UK gilt rate at the start of each year using historical rates — not today's rate applied backwards.

**Rebalancing:** Annual. Mid-year dividend cuts are held until the next rebalance — noted as a limitation.

**Benchmark:** FTSE 100 Total Return Index, which includes dividends reinvested. Not the price-only index.

**Performance metrics:** Annual return, cumulative return, Sharpe ratio, max drawdown.

**Data sources:**
- Stooq: historical daily price data for return calculations and CAPM beta, stored locally across three subfolders (1, 2, 3)
- FMP: historical financial statements (income statement, balance sheet, cash flow), dividend history, payout ratios
- yfinance: fallback for any tickers missing from FMP

**Caching:** All FMP responses saved to local CSV files on first run. All subsequent runs read from cache — no repeat API calls during development.

---

## File Structure

```
ScoreDCS/
├── main.py          — orchestrator, runs everything, produces final output
├── data_fetch.py    — all FMP and yfinance API calls, caching logic
├── scoring.py       — all existing three-pillar scoring logic
├── dupont.py        — DuPont decomposition module
├── capm.py          — CAPM expected return module
├── backtest.py      — backtest engine
├── universe.py      — full FTSE 100 + FTSE 250 ticker list
├── utils.py         — signal(), shared helper functions
├── cache/           — folder where FMP responses are stored locally
└── README.md        — methodology, limitations, results summary
```

---

## Day 1 — Refactor + DuPont + CAPM

### Morning — Refactor into modules (2–3 hours)
Split the existing ScoreDCS.py into the file structure above before writing any new code. Verify the existing tool still runs correctly after the split — do not proceed until it does.

### Afternoon — DuPont module (3–4 hours)
Pull net income, revenue, total assets, and equity from FMP historical data. Calculate:
- Net margin = net income / revenue
- Asset turnover = revenue / total assets
- Equity multiplier = total assets / equity

Their product must equal ROE — use this as a validation check. Add DuPont breakdown as additional output columns alongside the existing ROE score, do not replace it.

### Evening — CAPM module (3–4 hours)
Load 5 years of weekly price returns for each stock and the FTSE 250 index from Stooq local files — check all three subfolders (1, 2, 3) when loading. Use the historical UK 10-year gilt yield as Rf for each year — not a single fixed rate applied backwards. Calculate beta via covariance of stock returns with market returns divided by variance of market returns. Calculate E(r) = Rf + β(Rm − Rf). Flag stocks where current dividend yield exceeds E(r) as a basic undervaluation signal.

---

## Day 2 — Backtest Build Part 1

### Morning — Write README limitations section first, before any backtest code.
Document explicitly: survivorship bias, use of present-day constituents, point-in-time fundamental data limitations, no transaction costs, annual rebalancing ignores mid-year dividend cuts.

### Rest of Day 2 — Build backtest loop in backtest.py

**Step 1:** For each year 2019 to 2024, pull historical dividend yield for each stock in the universe at the start of that year from FMP. Filter to stocks yielding ≥4%.

**Step 2:** Run ScoreDCS scoring on each passing stock using that year's FMP financial statement data.

**Step 3:** Apply tiered position sizing rules. Allocate remainder to 1-year UK gilt at that year's historical rate.

**Step 4:** Record portfolio value at year end including dividends received and gilt income.

---

## Day 3 — Backtest Build Part 2 + Results

**Step 5:** Calculate and output annual return per year, cumulative return 2019–2024, Sharpe ratio using annual returns with gilt rate as risk-free rate, maximum drawdown across the period.

**Step 6:** Compare cumulative and annual returns against FTSE 100 Total Return Index.

**Step 7:** Produce clean output — year-by-year results table, benchmark comparison, summary statistics. This goes in the README and on GitHub.

**Step 8:** Push to GitHub with clean README covering methodology, design decisions, limitations, and results.

---

## Before You Write a Single Line of Code — Confirm These

1. Purchase FMP plan and confirm API key is working.
2. Test Stooq local files load correctly for at least 10 tickers across all three subfolders.
3. Verify FMP returns historical financials going back to 2019 for a sample of FTSE tickers before building the full backtest loop.
4. Decide now — full 350-stock universe or 50-stock pilot run first. Pilot run recommended to catch data and logic errors before scaling up.
