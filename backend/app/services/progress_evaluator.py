from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field


class ProgressMetrics(BaseModel):
    tests_passing: float = Field(default=0.0, ge=0.0, le=1.0)
    files_modified: float = Field(default=0.0, ge=0.0)
    errors_reduced: float = Field(default=0.0, ge=0.0, le=1.0)
    objective_completion: float = Field(default=0.0, ge=0.0, le=1.0)
    iteration_count: int = Field(default=0, ge=0)


class ProgressEvaluation(BaseModel):
    metrics: ProgressMetrics
    progress_score: float
    score_delta: float
    is_stuck: bool
    stop_report: str | None = None


@dataclass
class ProgressEvaluator:
    """Score runtime outcomes and detect repeated score declines."""

    stuck_after_declines: int = 3
    decline_count: int = 0
    previous_score: float | None = None

    def __post_init__(self) -> None:
        if self.stuck_after_declines <= 0:
            raise ValueError("stuck_after_declines must be greater than zero")

    def evaluate(
        self,
        metrics: ProgressMetrics | dict[str, Any] | None = None,
        *,
        previous_score: float | None = None,
        **metric_values: Any,
    ) -> ProgressEvaluation:
        values = {} if metrics is None else metrics.model_dump() if isinstance(metrics, ProgressMetrics) else dict(metrics)
        values.update(metric_values)
        current = ProgressMetrics.model_validate(values)
        score = self._score(current)
        baseline = self.previous_score if previous_score is None else previous_score
        delta = 0.0 if baseline is None else score - baseline
        if baseline is not None and delta < 0:
            self.decline_count += 1
        elif delta >= 0:
            self.decline_count = 0
        self.previous_score = score
        stuck = self.decline_count >= self.stuck_after_declines
        return ProgressEvaluation(
            metrics=current,
            progress_score=score,
            score_delta=delta,
            is_stuck=stuck,
            stop_report=self._report(current, score, delta) if stuck else None,
        )

    @staticmethod
    def _score(metrics: ProgressMetrics) -> float:
        return round(
            metrics.tests_passing * 0.35
            + min(metrics.files_modified / 10.0, 1.0) * 0.15
            + metrics.errors_reduced * 0.25
            + metrics.objective_completion * 0.25,
            4,
        )

    @staticmethod
    def _report(metrics: ProgressMetrics, score: float, delta: float) -> str:
        return (
            "Runtime stopped as STUCK because progress_score declined repeatedly. "
            f"progress_score={score:.4f}, delta={delta:.4f}, "
            f"tests_passing={metrics.tests_passing:.2f}, files_modified={metrics.files_modified:.0f}, "
            f"errors_reduced={metrics.errors_reduced:.2f}, objective_completion={metrics.objective_completion:.2f}, "
            f"iteration_count={metrics.iteration_count}."
        )
