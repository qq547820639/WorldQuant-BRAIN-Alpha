"""PortfolioConstructor — dollar-neutral long/short portfolio weights."""

from __future__ import annotations


class PortfolioConstructor:
    """Construct dollar-neutral long/short portfolios from daily alpha signals.

    Each day:
      - Long: top quantile stocks (positive weight proportional to rank)
      - Short: bottom quantile stocks (negative weight proportional to rank)
      - Remaining stocks: zero weight
    """

    def __init__(
        self, long_quantile: float = 0.2, short_quantile: float = 0.2
    ):
        self.long_quantile = long_quantile
        self.short_quantile = short_quantile

    def construct(self, alphas: list[list[float]]) -> list[list[float]]:
        """Build portfolio weights from alpha signals.

        Returns:
            2D list: [dates][symbols] of portfolio weights.
            Weights sum to 0.0 each day (dollar-neutral).
        """
        weights = []
        for day_alphas in alphas:
            n = len(day_alphas)
            if n == 0:
                weights.append([])
                continue

            # Sort by alpha value (ascending)
            indexed = sorted(enumerate(day_alphas), key=lambda x: x[1])
            n_long = max(1, int(n * self.long_quantile))
            n_short = max(1, int(n * self.short_quantile))

            day_weights = [0.0] * n
            # Short: bottom quantile (most negative alpha)
            for rank, (i, _) in enumerate(indexed[:n_short]):
                day_weights[i] = -1.0 / n_short
            # Long: top quantile (most positive alpha)
            for rank, (i, _) in enumerate(indexed[-n_long:]):
                day_weights[i] = 1.0 / n_long

            # Dollar-neutral check: force sum to zero
            total = sum(day_weights)
            if abs(total) > 1e-10:
                adjustment = total / n
                day_weights = [w - adjustment for w in day_weights]

            weights.append(day_weights)
        return weights


__all__ = ["PortfolioConstructor"]
