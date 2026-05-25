"""Advanced risk math — Aladdin/RiskMetrics-inspired estimators.

Upgrades over plain historical methods:
  - EWMA volatility (RiskMetrics 1996) — adapts to recent vol regimes
  - Ledoit-Wolf shrinkage covariance — stable correlation for small samples
  - Cornish-Fisher VaR — corrects for skew + kurtosis in return distribution

References:
  - J.P. Morgan, RiskMetrics Technical Document (1996)
  - Ledoit & Wolf (2004), "Honey, I Shrunk the Sample Covariance Matrix"
  - Cornish & Fisher (1937), Cornish-Fisher expansion
"""
from __future__ import annotations
import numpy as np
from scipy import stats


def ewma_volatility(returns: list[float] | np.ndarray,
                    lambda_decay: float = 0.94) -> float:
    """RiskMetrics EWMA daily vol. λ=0.94 is the standard for daily data.

    σ²_t = λ·σ²_{t-1} + (1-λ)·r²_{t-1}

    More responsive to recent vol regime changes than rolling-window std.
    """
    r = np.asarray(returns, dtype=float)
    if len(r) < 2:
        return 0.0
    var = float(r[0] ** 2)
    for ret in r[1:]:
        var = lambda_decay * var + (1 - lambda_decay) * (ret ** 2)
    return float(np.sqrt(var))


def ewma_covariance(returns_matrix: np.ndarray,
                    lambda_decay: float = 0.94) -> np.ndarray:
    """EWMA covariance matrix. returns_matrix: (T, N) — T days × N assets.

    Σ_t = λ·Σ_{t-1} + (1-λ)·r_{t-1}·r_{t-1}'
    """
    T, N = returns_matrix.shape
    if T < 2:
        return np.zeros((N, N))
    cov = np.outer(returns_matrix[0], returns_matrix[0])
    for t in range(1, T):
        r = returns_matrix[t]
        cov = lambda_decay * cov + (1 - lambda_decay) * np.outer(r, r)
    return cov


def ledoit_wolf_shrinkage(returns_matrix: np.ndarray) -> tuple[np.ndarray, float]:
    """Ledoit-Wolf shrinkage covariance estimator.

    Shrinks sample covariance toward a structured target (constant-correlation
    matrix) by an optimal amount α that minimizes expected MSE. Much more
    stable than sample covariance when T (observations) is small relative to N.

    Returns (shrunk_covariance, alpha) where alpha ∈ [0, 1] is the shrinkage
    intensity (0 = pure sample cov, 1 = full target).
    """
    X = np.asarray(returns_matrix, dtype=float)
    T, N = X.shape
    if T < 2 or N < 2:
        return np.cov(X.T) if T >= 2 else np.eye(N), 0.0

    # Sample covariance
    X_centered = X - X.mean(axis=0)
    S = (X_centered.T @ X_centered) / T

    # Target: constant-correlation matrix
    var = np.diag(S)
    sqrt_var = np.sqrt(var)
    R = S / np.outer(sqrt_var, sqrt_var)
    R[np.isnan(R)] = 0
    r_bar = (R.sum() - N) / (N * (N - 1))  # mean off-diagonal correlation
    F = r_bar * np.outer(sqrt_var, sqrt_var)
    np.fill_diagonal(F, var)

    # Compute optimal shrinkage intensity (simplified Ledoit-Wolf)
    pi_mat = np.zeros((N, N))
    for t in range(T):
        z = X_centered[t]
        pi_mat += (np.outer(z, z) - S) ** 2
    pi_hat = pi_mat.sum() / T

    gamma = ((F - S) ** 2).sum()
    if gamma < 1e-10:
        return S, 0.0

    rho_hat = pi_hat   # approximation; full LW computes rho more precisely
    kappa = (pi_hat - rho_hat) / gamma
    alpha = max(0.0, min(1.0, kappa / T))

    return alpha * F + (1 - alpha) * S, alpha


def cornish_fisher_var(returns: list[float] | np.ndarray,
                       confidence: float = 0.95) -> float:
    """Cornish-Fisher VaR — adjusts Gaussian quantile for skew + kurtosis.

    Better than historical VaR when the empirical distribution has fat tails
    or asymmetry (which most financial returns do).

    Returns positive %-loss at the given confidence (e.g. 2.5 means 2.5% loss).
    """
    r = np.asarray(returns, dtype=float)
    if len(r) < 30:
        # Fall back to historical for tiny samples
        return float(-np.percentile(r, (1 - confidence) * 100) * 100)

    mean = r.mean()
    std  = r.std(ddof=1)
    skew = stats.skew(r)
    kurt = stats.kurtosis(r)   # excess kurtosis (normal = 0)

    # Gaussian quantile at confidence level
    z = stats.norm.ppf(1 - confidence)

    # Cornish-Fisher expansion
    z_cf = (z
            + (z**2 - 1) * skew / 6
            + (z**3 - 3*z) * kurt / 24
            - (2*z**3 - 5*z) * skew**2 / 36)

    var_estimate = -(mean + z_cf * std)
    return float(var_estimate * 100)


def portfolio_var_ewma(returns_matrix: np.ndarray,
                       weights: list[float] | np.ndarray,
                       confidence: float = 0.95,
                       lambda_decay: float = 0.94) -> dict:
    """Portfolio VaR using EWMA covariance + parametric Gaussian quantile.

    Aladdin-style: forward-looking risk that reacts to current vol regime
    rather than averaging over the full history.
    """
    X = np.asarray(returns_matrix, dtype=float)
    w = np.asarray(weights, dtype=float)
    w = w / w.sum() if w.sum() else w

    cov = ewma_covariance(X, lambda_decay)
    port_var_daily = float(np.sqrt(w @ cov @ w))   # daily portfolio std

    z = stats.norm.ppf(1 - confidence)
    var_pct = float(-z * port_var_daily * 100)

    # Annualized vol
    ann_vol_pct = float(port_var_daily * np.sqrt(252) * 100)

    return {
        "var_pct_ewma":   round(var_pct, 4),
        "daily_vol_pct":  round(port_var_daily * 100, 4),
        "annual_vol_pct": round(ann_vol_pct, 4),
        "lambda":         lambda_decay,
        "method":         "EWMA-Parametric",
    }


def stress_var(returns: list[float] | np.ndarray,
               stress_multiplier: float = 1.5) -> float:
    """Stress-tested VaR — scale historical vol by a stress multiplier."""
    r = np.asarray(returns, dtype=float)
    if len(r) < 30:
        return 0.0
    stressed = r * stress_multiplier
    return float(-np.percentile(stressed, 5) * 100)


# ── GARCH(1,1) volatility forecast ───────────────────────────────────────────

def garch_11_forecast(returns: list[float] | np.ndarray,
                      horizon: int = 1) -> dict:
    """GARCH(1,1) volatility forecast — Bollerslev (1986).

    σ²_t = ω + α·r²_{t-1} + β·σ²_{t-1}

    Fits the model via MLE then forecasts h-step-ahead conditional variance.
    Better than EWMA for multi-step forecasts; captures mean-reversion to
    long-run vol level.

    Returns:
        omega, alpha, beta — fitted parameters
        long_run_vol       — unconditional vol = sqrt(ω / (1 − α − β))
        forecast_vol       — h-step forecasted daily vol
        persistence        — α + β (≈1 means highly persistent)
    """
    r = np.asarray(returns, dtype=float)
    n = len(r)
    if n < 60:
        return {"error": "Need ≥60 observations for GARCH"}

    r = r - r.mean()
    var_uncond = float(r.var())

    def neg_log_likelihood(params):
        omega, alpha, beta = params
        if omega <= 0 or alpha < 0 or beta < 0 or alpha + beta >= 1:
            return 1e10
        sigma2 = np.zeros(n)
        sigma2[0] = var_uncond
        for t in range(1, n):
            sigma2[t] = omega + alpha * r[t-1]**2 + beta * sigma2[t-1]
        ll = -0.5 * np.sum(np.log(2 * np.pi * sigma2) + r**2 / sigma2)
        return -ll

    try:
        from scipy.optimize import minimize
        x0 = [var_uncond * 0.05, 0.05, 0.90]
        result = minimize(
            neg_log_likelihood, x0,
            method="L-BFGS-B",
            bounds=[(1e-8, None), (1e-6, 0.5), (1e-6, 0.999)],
        )
        omega, alpha, beta = result.x
    except Exception as e:
        return {"error": f"GARCH fit failed: {e}"}

    persistence = alpha + beta
    long_run_var = omega / (1 - persistence) if persistence < 1 else var_uncond
    long_run_vol = float(np.sqrt(long_run_var))

    # Iterate forward h steps
    sigma2 = np.zeros(n)
    sigma2[0] = var_uncond
    for t in range(1, n):
        sigma2[t] = omega + alpha * r[t-1]**2 + beta * sigma2[t-1]

    last_sigma2 = sigma2[-1]
    last_r2     = r[-1]**2
    forecast_var = omega + alpha * last_r2 + beta * last_sigma2
    for _ in range(horizon - 1):
        forecast_var = omega + (alpha + beta) * forecast_var

    return {
        "omega":         round(float(omega), 8),
        "alpha":         round(float(alpha), 4),
        "beta":          round(float(beta), 4),
        "persistence":   round(float(persistence), 4),
        "long_run_vol":  round(long_run_vol, 6),
        "forecast_vol":  round(float(np.sqrt(forecast_var)), 6),
        "horizon":       horizon,
        "method":        "GARCH(1,1) MLE",
    }


# ── Risk Parity allocation ───────────────────────────────────────────────────

def risk_parity_weights(cov_matrix: np.ndarray,
                        max_iter: int = 200,
                        tol: float = 1e-8) -> np.ndarray:
    """Equal Risk Contribution (Risk Parity) portfolio weights.

    Maillard, Roncalli, Teïletche (2010). Each asset contributes equally
    to total portfolio risk — robust to estimation error vs Markowitz.

    Solves: minimize Σᵢ (RCᵢ − RC̄)² where RCᵢ = wᵢ·(Σw)ᵢ / √(w'Σw)
    via fixed-point iteration.
    """
    Sigma = np.asarray(cov_matrix, dtype=float)
    n = Sigma.shape[0]
    w = np.ones(n) / n

    for _ in range(max_iter):
        port_vol = np.sqrt(w @ Sigma @ w)
        if port_vol < 1e-12:
            break
        marginal = Sigma @ w / port_vol
        risk_contribs = w * marginal
        target_rc = port_vol / n
        # Newton-like update
        w_new = w * target_rc / (risk_contribs + 1e-12)
        w_new = w_new / w_new.sum()
        if np.abs(w_new - w).max() < tol:
            w = w_new
            break
        w = w_new

    return w


# ── Black-Litterman portfolio construction ───────────────────────────────────

def black_litterman(market_caps: np.ndarray,
                    cov_matrix: np.ndarray,
                    views_P: np.ndarray | None = None,
                    views_Q: np.ndarray | None = None,
                    views_omega: np.ndarray | None = None,
                    risk_aversion: float = 2.5,
                    tau: float = 0.025) -> dict:
    """Black-Litterman expected returns + posterior covariance.

    Combines (a) implied equilibrium returns from market caps with
    (b) investor views to produce regularised expected returns that don't
    over-fit historical means.

    Args:
        market_caps  : (N,) market cap weights of universe
        cov_matrix   : (N, N) prior covariance (use Ledoit-Wolf for stability)
        views_P      : (K, N) view matrix — each row specifies an absolute or
                       relative view (e.g. [1, 0, -1, 0] = "asset 0 outperforms asset 2")
        views_Q      : (K,) view returns (e.g. [0.02] = "2% outperformance")
        views_omega  : (K, K) view uncertainty (diagonal). If None, computed
                       from tau·P·Σ·P'
        risk_aversion: Sharpe-ratio implied; 2-3 typical for equities
        tau          : scaling factor (0.025 = 2.5% as common default)

    Returns dict with posterior expected returns, posterior covariance,
    optimal weights (mean-variance).
    """
    mkt_w = np.asarray(market_caps, dtype=float)
    mkt_w = mkt_w / mkt_w.sum()
    Sigma = np.asarray(cov_matrix, dtype=float)

    # Equilibrium implied returns: Π = λ·Σ·w_mkt
    pi = risk_aversion * Sigma @ mkt_w

    if views_P is None or views_Q is None:
        # No views — return equilibrium
        return {
            "expected_returns":     pi.tolist(),
            "posterior_covariance": Sigma.tolist(),
            "optimal_weights":      mkt_w.tolist(),
            "method":               "Black-Litterman (no views)",
        }

    P = np.asarray(views_P, dtype=float)
    Q = np.asarray(views_Q, dtype=float)
    if views_omega is None:
        Omega = np.diag(np.diag(tau * P @ Sigma @ P.T))
    else:
        Omega = np.asarray(views_omega, dtype=float)

    tau_Sigma = tau * Sigma
    try:
        # Posterior: E[R] = [(τΣ)⁻¹ + P'Ω⁻¹P]⁻¹ · [(τΣ)⁻¹Π + P'Ω⁻¹Q]
        inv_tau_sigma = np.linalg.inv(tau_Sigma)
        inv_omega     = np.linalg.inv(Omega)
        M_inv = inv_tau_sigma + P.T @ inv_omega @ P
        M = np.linalg.inv(M_inv)
        posterior_returns = M @ (inv_tau_sigma @ pi + P.T @ inv_omega @ Q)
        posterior_cov     = Sigma + M  # Meucci formulation
        # Optimal weights via MV
        opt_w = np.linalg.solve(risk_aversion * posterior_cov, posterior_returns)
        opt_w = np.clip(opt_w, 0, None)
        opt_w = opt_w / opt_w.sum() if opt_w.sum() > 0 else mkt_w
    except np.linalg.LinAlgError as e:
        return {"error": f"Singular matrix in Black-Litterman: {e}"}

    return {
        "expected_returns":     posterior_returns.tolist(),
        "posterior_covariance": posterior_cov.tolist(),
        "optimal_weights":      opt_w.tolist(),
        "equilibrium_returns":  pi.tolist(),
        "method":               "Black-Litterman with views",
    }


# ── Filtered Historical Simulation VaR ───────────────────────────────────────

def fhs_var(returns: list[float] | np.ndarray,
            confidence: float = 0.95,
            simulations: int = 5000) -> dict:
    """Filtered Historical Simulation VaR — Barone-Adesi, Giannopoulos (2002).

    Standardize returns by GARCH conditional vol, then resample standardized
    residuals and rescale by current vol. Captures fat tails + current regime.
    More robust than plain historical VaR when vol regime is changing.
    """
    r = np.asarray(returns, dtype=float)
    if len(r) < 60:
        return {"error": "Need ≥60 observations for FHS"}

    garch = garch_11_forecast(r.tolist(), horizon=1)
    if "error" in garch:
        return garch

    # Reconstruct conditional vols from GARCH
    omega, alpha, beta = garch["omega"], garch["alpha"], garch["beta"]
    r_centered = r - r.mean()
    sigma2 = np.zeros(len(r))
    sigma2[0] = r_centered.var()
    for t in range(1, len(r)):
        sigma2[t] = omega + alpha * r_centered[t-1]**2 + beta * sigma2[t-1]
    sigma = np.sqrt(sigma2)

    # Standardized residuals
    z = r_centered / sigma

    # Resample residuals, rescale by forecast vol
    forecast_vol = garch["forecast_vol"]
    rng = np.random.default_rng(seed=42)
    bootstrapped_z = rng.choice(z, size=simulations, replace=True)
    simulated_returns = bootstrapped_z * forecast_vol

    var_pct  = float(-np.percentile(simulated_returns, (1 - confidence) * 100) * 100)
    cvar_pct = float(-simulated_returns[simulated_returns <= np.percentile(simulated_returns, (1 - confidence) * 100)].mean() * 100)

    return {
        "var_fhs":      round(var_pct, 4),
        "cvar_fhs":     round(cvar_pct, 4),
        "garch":        garch,
        "n_simulated":  simulations,
        "method":       "Filtered Historical Simulation",
    }

