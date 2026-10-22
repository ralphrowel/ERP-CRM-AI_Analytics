"""Time-series demand forecasting engine for inventory replenishment.

Provides pure-Python, deterministic implementations of:
- Simple & Weighted Moving Averages (SMA, WMA)
- Single Exponential Smoothing (SES)
- Holt's Linear Trend (Double Exponential Smoothing)
- Holt-Winters Additive & Multiplicative (Triple Exponential Smoothing)
- Croston's Method for intermittent/sparse industrial demand
- Automated Best-Fit model selection with error metrics (MAE, RMSE, MAPE)
- Confidence interval prediction bands
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any


@dataclass
class ForecastPoint:
    date: str
    forecast: float
    lower_bound: float
    upper_bound: float


@dataclass
class ModelEvaluation:
    mae: float
    rmse: float
    mape: float


@dataclass
class ForecastOutput:
    model_name: str
    parameters: dict[str, Any]
    evaluation: ModelEvaluation
    historical_points: list[dict[str, Any]]
    forecast_points: list[ForecastPoint]
    total_forecast_demand: float
    average_daily_demand: float
    demand_std_dev: float
    intermittent_ratio: float  # Percentage of zero-demand periods
    model_diagnostics: dict[str, Any] = field(default_factory=dict)


def compute_metrics(actual: list[float], predicted: list[float]) -> ModelEvaluation:
    """Computes MAE, RMSE, and MAPE between actual and predicted values."""
    if not actual or not predicted or len(actual) != len(predicted):
        return ModelEvaluation(mae=0.0, rmse=0.0, mape=0.0)

    n = len(actual)
    abs_errors = [abs(a - p) for a, p in zip(actual, predicted, strict=True)]
    sq_errors = [(a - p) ** 2 for a, p in zip(actual, predicted, strict=True)]

    mae = sum(abs_errors) / n
    rmse = math.sqrt(sum(sq_errors) / n)

    # MAPE guarded against division by zero
    pct_errors = [
        abs(a - p) / a if a > 0.0001 else (0.0 if abs(a - p) < 0.0001 else 1.0)
        for a, p in zip(actual, predicted, strict=True)
    ]
    mape = (sum(pct_errors) / n) * 100.0

    return ModelEvaluation(
        mae=round(mae, 4),
        rmse=round(rmse, 4),
        mape=round(mape, 2),
    )


def simple_moving_average(series: list[float], horizon: int, window: int = 7) -> list[float]:
    """Simple Moving Average forecasting."""
    if not series:
        return [0.0] * horizon
    w = min(window, len(series))
    recent = series[-w:]
    avg = sum(recent) / len(recent)
    return [max(0.0, round(avg, 4))] * horizon


def single_exponential_smoothing(
    series: list[float], horizon: int, alpha: float = 0.2
) -> tuple[list[float], list[float]]:
    """Single Exponential Smoothing (SES).

    Returns (fitted_values, forecast_values).
    """
    if not series:
        return [], [0.0] * horizon

    fitted = [series[0]]
    level = series[0]
    for val in series[1:]:
        level = alpha * val + (1.0 - alpha) * level
        fitted.append(level)

    forecast = [max(0.0, round(level, 4))] * horizon
    return fitted, forecast


def holt_linear_trend(
    series: list[float],
    horizon: int,
    alpha: float = 0.3,
    beta: float = 0.1,
    damped: bool = True,
    phi: float = 0.95,
) -> tuple[list[float], list[float]]:
    """Holt's Linear Trend Exponential Smoothing with optional trend damping.

    Returns (fitted_values, forecast_values).
    """
    if not series:
        return [], [0.0] * horizon
    if len(series) == 1:
        return [series[0]], [max(0.0, series[0])] * horizon

    # Initialize level and trend
    level = series[0]
    trend = series[1] - series[0]
    fitted = [level]

    for val in series[1:]:
        last_level = level
        last_trend = trend
        damped_trend = phi * last_trend if damped else last_trend
        level = alpha * val + (1.0 - alpha) * (last_level + damped_trend)
        trend = beta * (level - last_level) + (1.0 - beta) * damped_trend
        fitted.append(last_level + damped_trend)

    forecast: list[float] = []
    current_phi = phi if damped else 1.0
    accumulated_trend = 0.0

    for _ in range(horizon):
        if damped:
            accumulated_trend += current_phi * trend
            current_phi *= phi
        else:
            accumulated_trend += trend

        fc = max(0.0, level + accumulated_trend)
        forecast.append(round(fc, 4))

    return fitted, forecast


def holt_winters(
    series: list[float],
    horizon: int,
    season_length: int = 7,
    alpha: float = 0.3,
    beta: float = 0.1,
    gamma: float = 0.2,
) -> tuple[list[float], list[float]]:
    """Holt-Winters Additive Triple Exponential Smoothing.

    Falls back to Holt's Linear Trend if series is shorter than 2 complete seasons.
    Returns (fitted_values, forecast_values).
    """
    n = len(series)
    if n < 2 * season_length:
        return holt_linear_trend(series, horizon, alpha=alpha, beta=beta)

    # Initial seasonals: average deviation from season mean
    season_averages = [
        sum(series[i : i + season_length]) / season_length
        for i in range(0, season_length * 2, season_length)
    ]
    seasonals = [
        ((series[i] - season_averages[0]) + (series[i + season_length] - season_averages[1])) / 2.0
        for i in range(season_length)
    ]

    level = sum(series[:season_length]) / season_length
    trend = (
        sum((series[season_length + i] - series[i]) / season_length for i in range(season_length))
        / season_length
    )

    fitted: list[float] = []

    for i in range(n):
        val = series[i]
        s_idx = i % season_length
        s_val = seasonals[s_idx]

        last_level = level
        last_trend = trend

        fit = last_level + last_trend + s_val
        fitted.append(fit)

        level = alpha * (val - s_val) + (1.0 - alpha) * (last_level + last_trend)
        trend = beta * (level - last_level) + (1.0 - beta) * last_trend
        seasonals[s_idx] = gamma * (val - level) + (1.0 - gamma) * s_val

    forecast: list[float] = []
    for h in range(1, horizon + 1):
        s_idx = (n + h - 1) % season_length
        fc = max(0.0, level + h * trend + seasonals[s_idx])
        forecast.append(round(fc, 4))

    return fitted, forecast


def croston_method(
    series: list[float], horizon: int, alpha: float = 0.1
) -> tuple[list[float], list[float]]:
    """Croston's Method for intermittent (lumpy/sparse) demand forecasting.

    Decomposes demand into non-zero demand size (z) and inter-arrival time (p).
    Forecast rate = z / p.
    """
    if not series:
        return [], [0.0] * horizon

    non_zero_values = [v for v in series if v > 0]
    if not non_zero_values:
        return [0.0] * len(series), [0.0] * horizon

    z = non_zero_values[0]
    p = 1.0
    q = 1
    fitted: list[float] = []

    for val in series:
        fitted.append(round(z / p, 4) if p > 0 else 0.0)
        if val > 0:
            z = alpha * val + (1.0 - alpha) * z
            p = alpha * q + (1.0 - alpha) * p
            q = 1
        else:
            q += 1

    rate = max(0.0, round(z / p, 4)) if p > 0 else 0.0
    forecast = [rate] * horizon
    return fitted, forecast


def generate_demand_forecast(
    historical_dates: list[date | str],
    historical_values: list[float],
    horizon_days: int = 30,
    model: str = "auto",
    season_length: int = 7,
) -> ForecastOutput:
    """Orchestrates model fitting, evaluation, and forecast projection with confidence intervals.

    Supported model strings: 'auto', 'holt_winters', 'holt_linear', 'croston', 'ses', 'sma'.
    """
    n = len(historical_values)
    if n == 0:
        return ForecastOutput(
            model_name="none",
            parameters={},
            evaluation=ModelEvaluation(0.0, 0.0, 0.0),
            historical_points=[],
            forecast_points=[],
            total_forecast_demand=0.0,
            average_daily_demand=0.0,
            demand_std_dev=0.0,
            intermittent_ratio=1.0,
        )

    # Basic historical statistics
    avg_demand = sum(historical_values) / n
    var = sum((x - avg_demand) ** 2 for x in historical_values) / max(1, n - 1)
    std_dev = math.sqrt(var)
    zero_count = sum(1 for x in historical_values if x <= 0.0001)
    intermittent_ratio = zero_count / n

    # Prepare candidate models
    candidates: dict[str, tuple[list[float], list[float], dict[str, Any]]] = {}

    # 1. Croston (strongly favored if intermittent_ratio > 0.40)
    cr_fit, cr_fc = croston_method(historical_values, horizon_days, alpha=0.15)
    candidates["croston"] = (cr_fit, cr_fc, {"alpha": 0.15})

    # 2. Holt Linear
    hl_fit, hl_fc = holt_linear_trend(
        historical_values, horizon_days, alpha=0.3, beta=0.1, damped=True
    )
    candidates["holt_linear"] = (
        hl_fit,
        hl_fc,
        {"alpha": 0.3, "beta": 0.1, "damped": True, "phi": 0.95},
    )

    # 3. Holt-Winters (if sufficient data)
    if n >= 2 * season_length:
        hw_fit, hw_fc = holt_winters(
            historical_values,
            horizon_days,
            season_length=season_length,
            alpha=0.3,
            beta=0.1,
            gamma=0.2,
        )
        candidates["holt_winters"] = (
            hw_fit,
            hw_fc,
            {"alpha": 0.3, "beta": 0.1, "gamma": 0.2, "season_length": season_length},
        )

    # 4. Single Exponential Smoothing
    ses_fit, ses_fc = single_exponential_smoothing(historical_values, horizon_days, alpha=0.25)
    candidates["ses"] = (ses_fit, ses_fc, {"alpha": 0.25})

    # 5. SMA
    sma_fc = simple_moving_average(historical_values, horizon_days, window=min(14, n))
    sma_fit = [avg_demand] * n
    candidates["sma"] = (sma_fit, sma_fc, {"window": min(14, n)})

    # Selection logic
    chosen_model = model.lower().strip()
    if chosen_model == "auto":
        # If demand is highly intermittent (> 45% zeroes), default to Croston or evaluate lowest RMSE
        if intermittent_ratio >= 0.45:
            chosen_model = "croston"
        else:
            best_model = "holt_linear"
            lowest_rmse = float("inf")
            for m_name, (m_fit, _, _) in candidates.items():
                eval_res = compute_metrics(historical_values, m_fit)
                if eval_res.rmse < lowest_rmse:
                    lowest_rmse = eval_res.rmse
                    best_model = m_name
            chosen_model = best_model

    if chosen_model not in candidates:
        chosen_model = "holt_linear" if "holt_linear" in candidates else "croston"

    fitted_values, forecast_values, params = candidates[chosen_model]
    evaluation = compute_metrics(historical_values, fitted_values)

    # Calculate residual standard error for confidence interval projection
    residuals = [a - p for a, p in zip(historical_values, fitted_values, strict=True)]
    res_var = sum(r**2 for r in residuals) / max(1, n - 1)
    se_residual = math.sqrt(res_var) if res_var > 0 else (std_dev if std_dev > 0 else 1.0)

    # Project forward dates
    last_dt_raw = historical_dates[-1]
    if isinstance(last_dt_raw, str):
        last_dt = date.fromisoformat(last_dt_raw)
    else:
        last_dt = last_dt_raw

    forecast_points: list[ForecastPoint] = []
    # z = 1.96 for 95% confidence
    z_score = 1.96

    for step, val in enumerate(forecast_values, start=1):
        target_date = last_dt + timedelta(days=step)
        margin = z_score * se_residual * math.sqrt(1.0 + (step * 0.05))
        lower = max(0.0, round(val - margin, 4))
        upper = round(val + margin, 4)

        forecast_points.append(
            ForecastPoint(
                date=target_date.isoformat(),
                forecast=val,
                lower_bound=lower,
                upper_bound=upper,
            )
        )

    # Format historical points
    historical_points = [
        {
            "date": (
                d.isoformat() if isinstance(d, date) else (str(d) if not isinstance(d, str) else d)
            ),
            "actual": val,
            "fitted": round(fitted_values[idx], 4) if idx < len(fitted_values) else val,
        }
        for idx, (d, val) in enumerate(zip(historical_dates, historical_values, strict=True))
    ]

    total_forecast = sum(p.forecast for p in forecast_points)

    return ForecastOutput(
        model_name=chosen_model,
        parameters=params,
        evaluation=evaluation,
        historical_points=historical_points,
        forecast_points=forecast_points,
        total_forecast_demand=round(total_forecast, 3),
        average_daily_demand=round(avg_demand, 3),
        demand_std_dev=round(std_dev, 3),
        intermittent_ratio=round(intermittent_ratio, 4),
        model_diagnostics={
            "data_points_count": n,
            "season_length": season_length,
            "residual_std_err": round(se_residual, 4),
        },
    )
