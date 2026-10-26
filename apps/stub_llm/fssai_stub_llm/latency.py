"""Response delay drawn from a log-normal distribution with a given mean and 95th percentile.

LLM latency is right-skewed: most calls are near the median, a few take several times longer. A
log-normal captures that with two numbers we can read off a provider's dashboard: mean and p95.

For X ~ LogNormal(mu, s):  mean = exp(mu + s²/2)   and   p95 = exp(mu + 1.645 s).
Dividing:  ln(p95/mean) = 1.645 s - s²/2,  so  s = 1.645 - sqrt(1.645² - 2 ln(p95/mean))  (the smaller root),
and mu = ln(mean) - s²/2. A p95/mean ratio above exp(1.645²/2) ≈ 3.87 has no solution; s is capped there.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

Z95 = 1.6448536269514722


@dataclass(frozen=True)
class LogNormal:
    mu: float
    sigma: float

    @classmethod
    def from_mean_p95(cls, mean_s: float, p95_s: float) -> LogNormal | None:
        """None means "no delay" (mean 0)."""
        if mean_s <= 0:
            return None
        ratio = max(p95_s / mean_s, 1.0)
        d = math.log(ratio)
        disc = Z95 * Z95 - 2 * d
        sigma = Z95 - math.sqrt(disc) if disc > 0 else Z95
        return cls(mu=math.log(mean_s) - sigma * sigma / 2, sigma=sigma)

    @property
    def mean(self) -> float:
        return math.exp(self.mu + self.sigma ** 2 / 2)

    @property
    def p95(self) -> float:
        return math.exp(self.mu + Z95 * self.sigma)

    def sample(self, rng: random.Random) -> float:
        return rng.lognormvariate(self.mu, self.sigma)
