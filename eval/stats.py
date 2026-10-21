"""Uncertainty and paired tests for query-level results.

Queries are clustered within songs (several lines and query types per song),
so confidence intervals resample songs, not queries.
"""
import math
import random
from collections import defaultdict

BOOTSTRAP_B = 2000


def cluster_bootstrap_ci(rows, value, cluster='song', b=BOOTSTRAP_B, seed=0, alpha=0.05):
    """95% percentile CI of mean(value(row)), resampling clusters with replacement."""
    groups = defaultdict(list)
    for r in rows:
        groups[r[cluster]].append(value(r))
    sums = [(sum(v), len(v)) for v in groups.values()]
    if not sums:
        return None
    rng = random.Random(seed)
    k = len(sums)
    means = []
    for _ in range(b):
        s = n = 0
        for _ in range(k):
            gs, gn = sums[rng.randrange(k)]
            s += gs
            n += gn
        means.append(s / n)
    means.sort()
    lo, hi = means[int(alpha / 2 * b)], means[int((1 - alpha / 2) * b) - 1]
    return [round(lo, 4), round(hi, 4)]


def mcnemar_exact(a_correct, b_correct):
    """Exact two-sided McNemar test on paired booleans. Returns discordant counts and p."""
    only_a = sum(1 for x, y in zip(a_correct, b_correct) if x and not y)
    only_b = sum(1 for x, y in zip(a_correct, b_correct) if y and not x)
    n = only_a + only_b
    if n == 0:
        return {'only_a': 0, 'only_b': 0, 'p_value': 1.0}
    k = min(only_a, only_b)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return {'only_a': only_a, 'only_b': only_b, 'p_value': min(1.0, 2 * tail)}
