"""Regime and change-point models used by A06 and A07 (spec sections 27, 28 and 79).

Pure numpy, deterministic and causal: every function only uses the data it is given,
and the agents only give it data up to the as-of date.

- ``return_matrix`` / ``market_returns``: daily log returns of a set of symbols, and their
  equal-weight average (a simple "market index" for the universe)
- ``fit_two_state_mixture``: 2-component Gaussian mixture fitted by EM (calm vs turbulent days)
- ``sticky_filter``: forward filter of a 2-state hidden Markov model that uses the mixture's
  components as emissions and a sticky transition matrix, so regimes do not flip-flop
- ``bocpd_run_length``: Adams-MacKay Bayesian online change-point detection
- ``average_correlation``: mean pairwise correlation of return columns
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from quantagents.market import FloatArray, MarketView

_LOG_2PI = math.log(2.0 * math.pi)


def return_matrix(view: MarketView, symbols: Sequence[str], n: int) -> FloatArray:
    """The last ``n`` daily log returns, one column per symbol (NaN where data is missing)."""
    if n < 1:
        raise ValueError("n must be >= 1")
    if not symbols:
        return np.empty((0, 0), dtype=np.float64)
    columns = []
    for symbol in symbols:
        close = np.asarray(view.close(symbol)[-(n + 1) :], dtype=np.float64)
        with np.errstate(divide="ignore", invalid="ignore"):
            r = np.diff(np.log(close))
        r[~np.isfinite(r)] = np.nan
        padded = np.full(n, np.nan)
        if len(r):
            padded[-len(r) :] = r
        columns.append(padded)
    return np.column_stack(columns)


def market_returns(view: MarketView, symbols: Sequence[str], n: int) -> FloatArray:
    """Equal-weight average of the symbols' log returns; only rows with data are kept."""
    matrix = return_matrix(view, symbols, n)
    if matrix.size == 0:
        return np.empty(0, dtype=np.float64)
    has_data = np.any(np.isfinite(matrix), axis=1)
    rows = matrix[has_data]
    counts = np.sum(np.isfinite(rows), axis=1)
    return np.asarray(np.nansum(rows, axis=1) / counts, dtype=np.float64)


@dataclass(frozen=True)
class Mixture:
    """Two Gaussian components; index 0 is always the calmer (lower variance) one."""

    weights: tuple[float, float]
    means: tuple[float, float]
    variances: tuple[float, float]
    log_likelihood: float
    iterations: int
    log_likelihood_one: float = -math.inf  # the same data with a single Gaussian
    n_obs: int = 0

    @property
    def variance_ratio(self) -> float:
        return self.variances[1] / self.variances[0]

    @property
    def bic_prefers_two(self) -> bool:
        """True when two components beat one by the Bayesian information criterion.

        EM always fits two components a little better than one, even on a single bell curve,
        so the extra 3 parameters must earn 1.5 x ln(n) of log-likelihood to count.
        """
        return self.log_likelihood - self.log_likelihood_one > 1.5 * math.log(max(self.n_obs, 2))


def _log_normal(x: FloatArray, mean: float, var: float) -> FloatArray:
    return np.asarray(-0.5 * (_LOG_2PI + math.log(var) + (x - mean) ** 2 / var), dtype=np.float64)


def fit_two_state_mixture(
    x: FloatArray, *, max_iter: int = 200, tol: float = 1e-9, var_floor_frac: float = 0.01
) -> Mixture:
    """Fit a 2-component Gaussian mixture by EM with a fixed, deterministic start.

    Start: both means at the sample mean, variances at 0.5x and 2x the sample variance.
    Variances are floored at ``var_floor_frac`` x the sample variance so a component can
    never collapse onto a single point.
    """
    data = np.asarray(x, dtype=np.float64)
    data = data[np.isfinite(data)]
    if len(data) < 10:
        raise ValueError("need at least 10 finite observations")
    mean, var = float(np.mean(data)), float(np.var(data))
    if var <= 0:
        raise ValueError("observations have zero variance")
    floor = var_floor_frac * var
    w = np.array([0.7, 0.3])
    mu = np.array([mean, mean])
    v = np.array([0.5 * var, 2.0 * var])
    previous = -math.inf
    log_lik = -math.inf
    iterations = 0
    for iterations in range(1, max_iter + 1):  # noqa: B007 (used after the loop)
        log_p = np.column_stack(
            [math.log(w[k]) + _log_normal(data, float(mu[k]), float(v[k])) for k in (0, 1)]
        )
        top = np.max(log_p, axis=1, keepdims=True)
        log_norm = top[:, 0] + np.log(np.sum(np.exp(log_p - top), axis=1))
        log_lik = float(np.sum(log_norm))
        resp = np.exp(log_p - log_norm[:, None])
        mass = np.maximum(resp.sum(axis=0), 1e-12)
        w = mass / len(data)
        w = np.clip(w, 1e-6, 1.0)
        w = w / w.sum()
        mu = (resp * data[:, None]).sum(axis=0) / mass
        v = np.maximum((resp * (data[:, None] - mu) ** 2).sum(axis=0) / mass, floor)
        if abs(log_lik - previous) <= tol * max(1.0, abs(log_lik)):
            break
        previous = log_lik
    order = (0, 1) if v[0] <= v[1] else (1, 0)
    return Mixture(
        weights=(float(w[order[0]]), float(w[order[1]])),
        means=(float(mu[order[0]]), float(mu[order[1]])),
        variances=(float(v[order[0]]), float(v[order[1]])),
        log_likelihood=log_lik,
        iterations=iterations,
        log_likelihood_one=float(np.sum(_log_normal(data, mean, var))),
        n_obs=len(data),
    )


def sticky_filter(x: FloatArray, mixture: Mixture, stay: float = 0.97) -> FloatArray:
    """P(turbulent state | returns up to t) for every t: a forward-only HMM filter.

    ``stay`` is the chance a regime carries on to the next day (0.97 means regimes last
    about 33 days on average). Forward-only means each value uses no later data.
    """
    if not 0.5 <= stay < 1.0:
        raise ValueError("stay must be in [0.5, 1)")
    data = np.asarray(x, dtype=np.float64)
    out = np.full(len(data), np.nan)
    prior_turbulent = mixture.weights[1]
    p = prior_turbulent
    for t, value in enumerate(data):
        predicted = stay * p + (1.0 - stay) * (1.0 - p)
        if not math.isfinite(float(value)):
            p = predicted
            out[t] = p
            continue
        log_calm = float(_log_normal(np.array([value]), mixture.means[0], mixture.variances[0])[0])
        log_turb = float(_log_normal(np.array([value]), mixture.means[1], mixture.variances[1])[0])
        top = max(log_calm, log_turb)
        a = (1.0 - predicted) * math.exp(log_calm - top)
        b = predicted * math.exp(log_turb - top)
        p = b / (a + b)
        out[t] = p
    return out


@dataclass(frozen=True)
class RunLength:
    """BOCPD result at the last observation."""

    p_recent_change: float  # P(the current regime started within the last ``recent`` bars)
    map_run_length: int  # most likely number of bars since the last change point
    n_obs: int


def _logsumexp(a: FloatArray) -> float:
    top = float(np.max(a))
    if not math.isfinite(top):
        return top
    return top + math.log(float(np.sum(np.exp(a - top))))


def bocpd_run_length(
    x: FloatArray,
    *,
    hazard: float = 1.0 / 250.0,
    recent: int = 10,
    max_run: int = 300,
    clip_sigmas: float = 4.0,
) -> RunLength:
    """Adams-MacKay (2007) Bayesian online change-point detection on returns.

    Returns are standardized by a robust scale (median absolute deviation) and clipped at
    ``clip_sigmas`` so one outlier day cannot fake a regime change. The model is Normal with
    unknown mean and variance (Normal-Gamma prior), so the predictive is a Student-t.
    """
    if not 0.0 < hazard < 1.0:
        raise ValueError("hazard must be in (0, 1)")
    data = np.asarray(x, dtype=np.float64)
    data = data[np.isfinite(data)]
    if len(data) < 2 * recent:
        raise ValueError(f"need at least {2 * recent} finite observations")
    centre = float(np.median(data))
    scale = 1.4826 * float(np.median(np.abs(data - centre)))
    if scale <= 0:
        scale = float(np.std(data)) or 1.0
    z = np.clip((data - centre) / scale, -clip_sigmas, clip_sigmas)

    mu0, kappa0, alpha0, beta0 = 0.0, 1.0, 1.0, 1.0
    size = min(len(z), max_run) + 1
    nu_all = 2.0 * alpha0 + np.arange(size, dtype=np.float64)
    lg = np.array([math.lgamma((n + 1.0) / 2.0) - math.lgamma(n / 2.0) for n in nu_all])
    log_h, log_1mh = math.log(hazard), math.log1p(-hazard)

    log_r = np.array([0.0])
    mu = np.array([mu0])
    kappa = np.array([kappa0])
    alpha = np.array([alpha0])
    beta = np.array([beta0])
    for value in z:
        k = len(log_r)
        # Student-t predictive for each run length (index r has seen r observations).
        nu = 2.0 * alpha
        scale2 = beta * (kappa + 1.0) / (alpha * kappa)
        log_pred = (
            lg[:k]
            - 0.5 * np.log(nu * math.pi * scale2)
            - (nu + 1.0) / 2.0 * np.log1p((value - mu) ** 2 / (nu * scale2))
        )
        joint = log_r + log_pred
        log_cp = _logsumexp(joint) + log_h  # a new regime starts now
        new_log_r = np.concatenate([[log_cp], joint + log_1mh])  # or every run grows by one
        # Conjugate Normal-Gamma update of every run's parameters with this observation.
        new_beta = beta + kappa * (value - mu) ** 2 / (2.0 * (kappa + 1.0))
        mu = np.concatenate([[mu0], (kappa * mu + value) / (kappa + 1.0)])
        kappa = np.concatenate([[kappa0], kappa + 1.0])
        alpha = np.concatenate([[alpha0], alpha + 0.5])
        beta = np.concatenate([[beta0], new_beta])
        if len(new_log_r) > size:
            new_log_r, mu, kappa = new_log_r[:size], mu[:size], kappa[:size]
            alpha, beta = alpha[:size], beta[:size]
        log_r = new_log_r - _logsumexp(new_log_r)
    probs = np.exp(log_r)
    return RunLength(
        p_recent_change=min(1.0, float(np.sum(probs[:recent]))),
        map_run_length=int(np.argmax(probs)),
        n_obs=len(z),
    )


def average_correlation(matrix: FloatArray) -> float:
    """Mean off-diagonal correlation of the columns (rows with any NaN are dropped)."""
    m = np.asarray(matrix, dtype=np.float64)
    if m.ndim != 2 or m.shape[1] < 2:
        return math.nan
    rows = m[np.all(np.isfinite(m), axis=1)]
    if len(rows) < 3:
        return math.nan
    std = rows.std(axis=0)
    keep = std > 0
    if np.count_nonzero(keep) < 2:
        return math.nan
    corr = np.asarray(np.corrcoef(rows[:, keep], rowvar=False), dtype=np.float64)
    n = int(np.count_nonzero(keep))
    return float((float(np.sum(corr)) - n) / (n * (n - 1)))
