import sqlite3
import os

_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "uk_equity_library.db")

# Macro constants
RF        = 0.044   # UK risk-free rate (10Y gilt)
ERP       = 0.046   # UK equity risk premium
TAX_RATE  = 0.25    # UK corporation tax
TERM_GROW = 0.025   # terminal growth rate (UK long-run GDP)
FORECAST_YEARS = 5

# Growth caps — prevent absurd extrapolation from volatile FCF
MAX_GROWTH =  0.30
MIN_GROWTH = -0.30


def _get_db_data(ticker):
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row

    fin_rows = conn.execute("""
        SELECT year, free_cash_flow, ebit, total_debt, total_equity
        FROM financials
        WHERE ticker = ? AND free_cash_flow IS NOT NULL
        ORDER BY year DESC LIMIT 5
    """, (ticker,)).fetchall()

    price_row = conn.execute("""
        SELECT close FROM prices WHERE ticker = ? ORDER BY date DESC LIMIT 1
    """, (ticker,)).fetchone()

    company = conn.execute(
        "SELECT beta FROM companies WHERE ticker = ?", (ticker,)
    ).fetchone()

    # Use FCF / fcf_yield to get market cap in GBP (avoids USD/GBX mismatch in companies table)
    fund_row = conn.execute("""
        SELECT fcf_yield FROM fundamentals
        WHERE ticker = ? AND fcf_yield IS NOT NULL AND fcf_yield > 0
        ORDER BY year DESC LIMIT 1
    """, (ticker,)).fetchone()

    conn.close()
    return fin_rows, price_row, company, fund_row


def _historical_fcf_growth(fin_rows):
    """Average YoY FCF growth over available years (up to 4 growth periods)."""
    fcfs = [(r["year"], r["free_cash_flow"]) for r in fin_rows
            if r["free_cash_flow"] and r["free_cash_flow"] != 0]
    fcfs = sorted(fcfs, key=lambda x: x[0])  # ascending

    if len(fcfs) < 2:
        return 0.05  # default 5% if insufficient history

    growth_rates = []
    for i in range(1, len(fcfs)):
        prev = fcfs[i - 1][1]
        curr = fcfs[i][1]
        if prev > 0:  # only meaningful when base FCF is positive
            growth_rates.append((curr - prev) / prev)

    if not growth_rates:
        return 0.05

    avg = sum(growth_rates) / len(growth_rates)
    return max(MIN_GROWTH, min(MAX_GROWTH, avg))


def _compute_wacc(fin_rows, beta):
    """Compute WACC from capital structure and beta."""
    latest = fin_rows[0] if fin_rows else None

    cost_of_equity = RF + (beta or 1.0) * ERP

    if latest and latest["total_debt"] and latest["total_equity"]:
        debt   = latest["total_debt"]
        equity = latest["total_equity"]
        total  = debt + equity
        if total <= 0:
            return cost_of_equity

        # Implied cost of debt from EBIT/total_debt
        if latest["ebit"] and latest["ebit"] > 0 and debt > 0:
            cost_of_debt = min(latest["ebit"] / debt, 0.15)  # cap at 15%
        else:
            cost_of_debt = 0.05  # default

        we = equity / total
        wd = debt   / total
        wacc = (we * cost_of_equity) + (wd * cost_of_debt * (1 - TAX_RATE))
    else:
        wacc = cost_of_equity

    # WACC must exceed terminal growth rate to avoid negative terminal value
    return max(wacc, TERM_GROW + 0.02)


def _dcf_value(base_fcf, growth_rate, wacc):
    """Discount FCF over forecast period + terminal value. Returns total PV."""
    pv_fcfs = 0
    fcf = base_fcf
    for t in range(1, FORECAST_YEARS + 1):
        fcf *= (1 + growth_rate)
        pv_fcfs += fcf / (1 + wacc) ** t

    # Gordon Growth Model terminal value
    terminal_fcf = fcf * (1 + TERM_GROW)
    terminal_value = terminal_fcf / (wacc - TERM_GROW)
    pv_terminal = terminal_value / (1 + wacc) ** FORECAST_YEARS

    return pv_fcfs + pv_terminal


def _intrinsic_per_share(total_value, debt, base_fcf, fcf_yield, current_price):
    """
    Equity value = firm value - net debt.
    Shares derived from FCF / fcf_yield (GBP market cap) / price_GBP.
    LSE prices are in GBX (pence) so divide by 100 to get GBP.
    Returns "debt>value" string when debt exceeds DCF firm value (insolvent on DCF basis).
    """
    if not current_price or not base_fcf or not fcf_yield:
        return None
    equity_value = total_value - (debt or 0)
    if equity_value <= 0:
        return "debt>value"
    market_cap_gbp = base_fcf / fcf_yield
    price_gbp = current_price / 100  # GBX → GBP
    shares = market_cap_gbp / price_gbp
    return (equity_value / shares) * 100  # return in GBX to match current price


def dcf(ticker):
    fin_rows, price_row, company, fund_row = _get_db_data(ticker)

    if not fin_rows:
        return _empty_result(ticker, "No financial data in DB")

    current_price = price_row["close"] if price_row else None
    beta          = company["beta"] if company else 1.0
    fcf_yield     = fund_row["fcf_yield"] if fund_row else None

    base_fcf  = fin_rows[0]["free_cash_flow"]
    debt      = fin_rows[0]["total_debt"] or 0

    if not base_fcf or base_fcf <= 0:
        return _empty_result(ticker, "Negative or zero base FCF — DCF not meaningful")

    if not fcf_yield:
        return _empty_result(ticker, "FCF yield unavailable — cannot compute shares outstanding")

    base_growth = _historical_fcf_growth(fin_rows)
    wacc        = _compute_wacc(fin_rows, beta)

    # Flag financials/banks — low WACC driven by high debt weighting, DCF structurally unreliable
    is_financial = wacc < 0.05

    # --- Base case ---
    base_value     = _dcf_value(base_fcf, base_growth, wacc)
    base_per_share = _intrinsic_per_share(base_value, debt, base_fcf, fcf_yield, current_price)

    # --- Bull / Bear scenarios (±5% on growth, note if already at cap/floor) ---
    bull_growth      = min(base_growth + 0.05, MAX_GROWTH)
    bear_growth      = max(base_growth - 0.05, MIN_GROWTH)
    bull_at_cap      = bull_growth == MAX_GROWTH
    bear_at_floor    = bear_growth == MIN_GROWTH and (base_growth - 0.05) < MIN_GROWTH

    bull_value     = _dcf_value(base_fcf, bull_growth, wacc)
    bear_value     = _dcf_value(base_fcf, bear_growth, wacc)
    bull_per_share = _intrinsic_per_share(bull_value, debt, base_fcf, fcf_yield, current_price)
    bear_per_share = _intrinsic_per_share(bear_value, debt, base_fcf, fcf_yield, current_price)

    # --- Margin of safety ---
    if base_per_share and isinstance(base_per_share, float) and current_price:
        margin_of_safety = (base_per_share - current_price) / base_per_share
    else:
        margin_of_safety = None

    # --- Sensitivity table: WACC ±1% (3 steps) × growth ±2% (3 steps) ---
    sensitivity = {}
    for w_adj in [-0.01, 0.0, 0.01]:
        w = round(wacc + w_adj, 4)
        if w <= TERM_GROW:
            continue
        sensitivity[f"WACC {round(w*100,1)}%"] = {}
        for g_adj in [-0.02, 0.0, 0.02]:
            g = round(base_growth + g_adj, 4)
            g = max(MIN_GROWTH, min(MAX_GROWTH, g))
            val = _dcf_value(base_fcf, g, w)
            ps  = _intrinsic_per_share(val, debt, base_fcf, fcf_yield, current_price)
            sensitivity[f"WACC {round(w*100,1)}%"][f"Growth {round(g*100,1)}%"] = (
                round(ps, 2) if isinstance(ps, float) else ps
            )

    def _fmt(val):
        if val is None:
            return None
        if isinstance(val, str):
            return val  # passthrough "debt>value"
        return round(val, 2)

    return {
        "Ticker":              ticker,
        "Current Price":       round(current_price, 2) if current_price else None,
        "Base FCF (£m)":       round(base_fcf / 1e6, 1),
        "FCF Growth (base)":   round(base_growth * 100, 2),
        "WACC (%)":            round(wacc * 100, 2),
        "Terminal Growth (%)": round(TERM_GROW * 100, 2),
        "Intrinsic Value (Base)": _fmt(base_per_share),
        "Intrinsic Value (Bull)": _fmt(bull_per_share) if not bull_at_cap else f"{_fmt(bull_per_share)} (at growth cap)",
        "Intrinsic Value (Bear)": _fmt(bear_per_share) if not bear_at_floor else f"{_fmt(bear_per_share)} (at growth floor)",
        "Margin of Safety":    round(margin_of_safety * 100, 2) if margin_of_safety is not None else None,
        "Sensitivity":         sensitivity,
        "Note":                "DCF unreliable for financial/bank stocks — low WACC driven by debt structure" if is_financial else None,
    }


def _empty_result(ticker, note):
    return {
        "Ticker": ticker,
        "Current Price": None,
        "Base FCF (£m)": None,
        "FCF Growth (base)": None,
        "WACC (%)": None,
        "Terminal Growth (%)": round(TERM_GROW * 100, 2),
        "Intrinsic Value (Base)": None,
        "Intrinsic Value (Bull)": None,
        "Intrinsic Value (Bear)": None,
        "Margin of Safety": None,
        "Sensitivity": {},
        "Note": note,
    }


def print_dcf(ticker):
    """Pretty-print DCF output for a single ticker."""
    r = dcf(ticker)
    print(f"\n{'='*55}")
    print(f"  DCF Valuation — {r['Ticker']}")
    print(f"{'='*55}")

    # Notes that prevent meaningful output — skip remainder
    if r["Note"] and r["Base FCF (£m)"] is None:
        print(f"  Note: {r['Note']}")
        return

    print(f"  Current Price:        {r['Current Price']}")
    print(f"  Base FCF:             £{r['Base FCF (£m)']}m")
    print(f"  FCF Growth (base):    {r['FCF Growth (base)']}%")
    print(f"  WACC:                 {r['WACC (%)']}%")
    print(f"  Terminal Growth:      {r['Terminal Growth (%)']}%")

    # Show warning note inline if present (e.g. financial/bank flag)
    if r["Note"]:
        print(f"  ⚠ Warning:           {r['Note']}")

    print()
    print(f"  Intrinsic Value:")
    base = r['Intrinsic Value (Base)']
    bear = r['Intrinsic Value (Bear)']
    bull = r['Intrinsic Value (Bull)']
    print(f"    Bear case:          {bear if bear is not None else 'debt exceeds DCF value'}")
    print(f"    Base case:          {base if base is not None else 'debt exceeds DCF value'}")
    print(f"    Bull case:          {bull if bull is not None else 'debt exceeds DCF value'}")
    print()

    mos = r["Margin of Safety"]
    if mos is not None:
        direction = "undervalued" if mos > 0 else "overvalued"
        print(f"  Margin of Safety:     {mos}%  ({direction})")
    else:
        print(f"  Margin of Safety:     N/A (debt exceeds DCF value in base case)")
    print()

    if r["Sensitivity"]:
        print(f"  Sensitivity (Intrinsic Value per Share):")
        print(f"  {'':20}", end="")
        first_wacc = next(iter(r["Sensitivity"]))
        growth_keys = list(r["Sensitivity"][first_wacc].keys())
        for g in growth_keys:
            print(f"  {g:>16}", end="")
        print()
        for wacc_label, growth_vals in r["Sensitivity"].items():
            print(f"  {wacc_label:20}", end="")
            for g in growth_keys:
                val = growth_vals.get(g)
                display = str(val) if val not in (None, "debt>value") else "debt>value"
                print(f"  {display:>16}", end="")
            print()
    print()
