# Ranking methodology

Rankings order what was measured; they are not recommendations.

1. Only runs at the **realistic cost level** are ranked (retail Kraken fees for crypto, base stock costs).
2. Candidates (positive expectancy on train and validation, >= 30 trades) are ranked above non-candidates.
3. Within each group, runs are ordered by full-period expectancy in R per trade.
4. Every ranked row also shows: trade count, win rate, net return, Sharpe, max drawdown, expectancy before costs,
   the share of positive walk-forward folds, the untouched test-segment expectancy (for candidates), and whether the
   result survives Holm correction. A high rank with few trades, negative folds or a non-significant Holm result
   should be read as noise.
5. The strategy-level "measured" figure in the Library tab is the best instrument's realistic-cost expectancy,
   which is itself a selection over instruments and therefore optimistic.
