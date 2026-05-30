import sqlite3
import os

_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "UKStocksLibrary", "data", "uk_equity_library.db")

# Minimum ScoreDCS Total Score (0-100) to be included in portfolio
MIN_SCORE = 67.0

# Maximum weight any single stock can hold
MAX_WEIGHT = 0.15


def score_weighted(scored_tickers, min_score=MIN_SCORE, max_weight=MAX_WEIGHT):
    """
    Build a score-weighted portfolio from a list of (ticker, total_score) tuples.

    Steps:
      1. Filter to stocks scoring above min_score
      2. Assign raw weight proportional to Total Score
      3. Apply max_weight cap — redistribute excess to remaining stocks iteratively
      4. Normalise weights to sum to 1.0

    Args:
        scored_tickers: list of (ticker, total_score) where total_score is 0-100
        min_score:       minimum score threshold to include in portfolio
        max_weight:      maximum weight per stock (default 10%)

    Returns dict with:
        weights         — {ticker: weight}
        n_stocks        — number of stocks in portfolio
        avg_score       — average score of included stocks
        min_score_used  — threshold applied
    """
    # Filter and sort by score descending
    eligible = [(t, s) for t, s in scored_tickers if s is not None and s >= min_score]

    if not eligible:
        return {"weights": {}, "n_stocks": 0, "avg_score": None, "min_score_used": min_score}

    # Iterative capping — redistribute excess weight until all weights are within cap
    weights = {t: s for t, s in eligible}

    for _ in range(100):  # max iterations
        total = sum(weights.values())
        if total == 0:
            break
        normalised = {t: w / total for t, w in weights.items()}

        capped    = {t: min(w, max_weight) for t, w in normalised.items()}
        uncapped  = {t: w for t, w in normalised.items() if w < max_weight}

        if not uncapped:
            weights = capped
            break

        excess = sum(normalised[t] - max_weight for t in normalised if normalised[t] > max_weight)
        if excess < 1e-9:
            weights = capped
            break

        # Redistribute excess proportionally to uncapped stocks
        uncapped_total = sum(weights[t] for t in uncapped)
        for t in weights:
            if t in uncapped:
                weights[t] = weights[t] + (weights[t] / uncapped_total) * excess * total
            else:
                weights[t] = max_weight * total

    # Final normalisation
    total = sum(weights.values())
    weights = {t: round(w / total, 6) for t, w in weights.items()}

    avg_score = sum(s for _, s in eligible) / len(eligible)

    return {
        "weights":        weights,
        "n_stocks":       len(eligible),
        "avg_score":      round(avg_score, 2),
        "min_score_used": min_score,
    }


def print_score_weighted(result):
    print(f"\n{'='*50}")
    print(f"  Score-Weighted Portfolio")
    print(f"{'='*50}")
    if not result["weights"]:
        print("  No stocks passed the minimum score threshold.")
        return
    print(f"  Stocks included:   {result['n_stocks']}")
    print(f"  Avg ScoreDCS:      {result['avg_score']}%")
    print(f"  Min score cutoff:  {result['min_score_used']}%")
    print(f"  Max weight cap:    10%")
    print()
    print(f"  {'Ticker':<12} {'Weight':>8}")
    print(f"  {'-'*22}")
    for ticker, weight in sorted(result["weights"].items(), key=lambda x: -x[1]):
        print(f"  {ticker:<12} {weight*100:>7.2f}%")
    print(f"  {'-'*22}")
    print(f"  {'Total':<12} {sum(result['weights'].values())*100:>7.2f}%")
    print()
