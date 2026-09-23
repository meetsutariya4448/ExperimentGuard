"""Beta-Binomial posterior comparison, reported as a cross-check and never as a gate.

The quantity of interest is P(RR > c) where RR = p_treatment / p_reference and
c = 1 + theta:

    P(T/R > c) = integral over r in [0, 1/c] of  pdf_R(r) * sf_T(c * r)  dr

Two traps, both confirmed numerically before this module was written:

1. `integral of pdf_T(x) * cdf_R(x) dx` is a *different* quantity -- it is P(T > R),
   i.e. the c = 1 case. It ignores theta entirely and silently returns the same
   number for every threshold.

2. Integrating naively over [0, 1/c] fails on concentrated posteriors. Plain
   `scipy.integrate.quad` returns 0.0 where the true value is 1.0 at n = 200k,
   because the sampled abscissae miss the posterior's razor-thin support. This is
   a silent wrong answer, not a precision warning.

The fix is to integrate over the *reference posterior's effective support*
(its eps and 1-eps quantiles, clipped to 1/c) using fixed-order Gauss-Legendre
quadrature. Because the domain is rescaled per comparison, concentration is handled
by construction, and the whole thing vectorises across comparisons.

Cost note, measured rather than assumed: the survival function dominates. SciPy's
`betaincc` (which `beta.sf` calls) runs at roughly 22k elements/second at the
parameter magnitudes here, while the pdf is ~300x faster. Node count is therefore
the cost lever. Measured against a 256-node reference, 48 nodes already agree to
3e-14 and 32 nodes to 2e-9, so 64 nodes is generous: it buys machine-precision
agreement at about 98 seconds for a one-comparison-per-experiment pass over the
full 32,487-experiment archive. Raising it further costs time and buys nothing.
"""

from __future__ import annotations

import numpy as np
from scipy import optimize, stats

__all__ = [
    "posterior_params",
    "prob_ratio_exceeds",
    "expected_loss",
    "ratio_credible_interval",
]

# 64 nodes: machine-precision agreement with a 256-node reference (3.3e-14 across
# sample sizes from 3e3 to 2e6, near-null cases and zero-click arms), at a quarter
# of the survival-function cost. See the cost note above.
_QUAD_NODES = 64
_GL_NODES, _GL_WEIGHTS = np.polynomial.legendre.leggauss(_QUAD_NODES)


def posterior_params(
    clicks, impressions, prior_alpha: float = 1.0, prior_beta: float = 1.0
) -> tuple[np.ndarray, np.ndarray]:
    """Conjugate Beta posterior parameters for a binomial arm."""
    clicks = np.asarray(clicks, dtype=float)
    impressions = np.asarray(impressions, dtype=float)
    return prior_alpha + clicks, prior_beta + (impressions - clicks)


def prob_ratio_exceeds(a_t, b_t, a_r, b_r, c: float = 1.05, eps: float = 1e-12) -> np.ndarray:
    """P(T/R > c) for Beta(a_t, b_t) treatment and Beta(a_r, b_r) reference.

    Vectorised over the parameter arrays. Accurate on concentrated posteriors:
    validated against a 2,000,000-draw Monte Carlo to within 4e-4 across sample
    sizes from 3e3 to 2e6, near-null cases, and zero-click arms in either position.

    This is the expensive primitive in the codebase (see the module cost note), so
    call it once per experiment for the winner against its strongest rival rather
    than for every ordered pair.
    """
    a_t, b_t, a_r, b_r = (np.atleast_1d(np.asarray(x, dtype=float)) for x in (a_t, b_t, a_r, b_r))
    a_t, b_t, a_r, b_r = np.broadcast_arrays(a_t, b_t, a_r, b_r)

    # Integrate only where the reference posterior actually has mass.
    lo = stats.beta.ppf(eps, a_r, b_r)
    hi = np.minimum(stats.beta.ppf(1.0 - eps, a_r, b_r), 1.0 / c)

    out = np.zeros(a_t.shape, dtype=float)
    live = hi > lo
    if np.any(live):
        lo_l, hi_l = lo[live], hi[live]
        half = 0.5 * (hi_l - lo_l)
        mid = 0.5 * (hi_l + lo_l)
        # shape: (n_live, n_nodes)
        r = mid[:, None] + half[:, None] * _GL_NODES[None, :]
        integrand = stats.beta.pdf(r, a_r[live][:, None], b_r[live][:, None]) * stats.beta.sf(
            c * r, a_t[live][:, None], b_t[live][:, None]
        )
        out[live] = half * np.einsum("ij,j->i", integrand, _GL_WEIGHTS)

    # Mass of R below the integration floor. Bounded by eps, carried for exactness.
    out += stats.beta.cdf(lo, a_r, b_r) * stats.beta.sf(c * lo, a_t, b_t)
    return np.clip(out, 0.0, 1.0)


def expected_loss(a_t, b_t, a_r, b_r, eps: float = 1e-12) -> np.ndarray:
    """E[max(0, p_reference - p_treatment)] -- the cost of wrongly choosing treatment.

    Uses the closed form for the inner truncated mean,
    integral over [0, r] of t * pdf_T(t) dt = mean_T * cdf_{Beta(a_t + 1, b_t)}(r),
    leaving a single well-behaved outer integral over the reference posterior.
    """
    a_t, b_t, a_r, b_r = (np.atleast_1d(np.asarray(x, dtype=float)) for x in (a_t, b_t, a_r, b_r))
    a_t, b_t, a_r, b_r = np.broadcast_arrays(a_t, b_t, a_r, b_r)

    lo = stats.beta.ppf(eps, a_r, b_r)
    hi = stats.beta.ppf(1.0 - eps, a_r, b_r)
    mean_t = a_t / (a_t + b_t)

    out = np.zeros(a_t.shape, dtype=float)
    live = hi > lo
    if np.any(live):
        half = 0.5 * (hi[live] - lo[live])
        mid = 0.5 * (hi[live] + lo[live])
        r = mid[:, None] + half[:, None] * _GL_NODES[None, :]
        at, bt = a_t[live][:, None], b_t[live][:, None]
        inner = r * stats.beta.cdf(r, at, bt) - mean_t[live][:, None] * stats.beta.cdf(
            r, at + 1.0, bt
        )
        integrand = stats.beta.pdf(r, a_r[live][:, None], b_r[live][:, None]) * inner
        out[live] = half * np.einsum("ij,j->i", integrand, _GL_WEIGHTS)
    return np.maximum(out, 0.0)


def ratio_credible_interval(
    a_t: float, b_t: float, a_r: float, b_r: float, alpha: float = 0.05, eps: float = 1e-12
) -> tuple[float | None, float | None]:
    """Equal-tailed credible interval for RR, by inverting `prob_ratio_exceeds`.

    Scalar-only: this root-finds, so it is for single-experiment drill-down rather
    than archive-wide computation.
    """

    def solve(target: float) -> float | None:
        def f(log_c: float) -> float:
            return (
                float(prob_ratio_exceeds(a_t, b_t, a_r, b_r, c=np.exp(log_c), eps=eps)[0]) - target
            )

        lo_log, hi_log = np.log(1e-6), np.log(1e6)
        if f(lo_log) < 0 or f(hi_log) > 0:
            return None
        try:
            return float(np.exp(optimize.brentq(f, lo_log, hi_log, xtol=1e-10, rtol=1e-12)))
        except (ValueError, RuntimeError):
            return None

    return solve(1.0 - alpha / 2.0), solve(alpha / 2.0)
