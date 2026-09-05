from __future__ import annotations

from app.services.progress_evaluator import ProgressEvaluator


def test_progress_evaluator_scores_metrics_and_detects_repeated_declines() -> None:
    evaluator = ProgressEvaluator(stuck_after_declines=2)
    first = evaluator.evaluate({"tests_passing": 0.8, "files_modified": 4, "errors_reduced": 0.6, "objective_completion": 0.5, "iteration_count": 1})
    second = evaluator.evaluate({"tests_passing": 0.6, "files_modified": 2, "errors_reduced": 0.4, "objective_completion": 0.3, "iteration_count": 2})
    third = evaluator.evaluate({"tests_passing": 0.4, "files_modified": 1, "errors_reduced": 0.2, "objective_completion": 0.1, "iteration_count": 3})

    assert first.progress_score > 0
    assert second.score_delta < 0
    assert third.is_stuck is True
    assert "STUCK" in (third.stop_report or "")
    assert "progress_score" in (third.stop_report or "")


def test_progress_evaluator_resets_decline_count_when_score_recovers() -> None:
    evaluator = ProgressEvaluator(stuck_after_declines=2)
    evaluator.evaluate({"tests_passing": 0.8, "errors_reduced": 0.8, "objective_completion": 0.8})
    evaluator.evaluate({"tests_passing": 0.4, "errors_reduced": 0.4, "objective_completion": 0.4})
    recovered = evaluator.evaluate({"tests_passing": 1.0, "errors_reduced": 1.0, "objective_completion": 1.0})

    assert recovered.is_stuck is False
    assert recovered.score_delta > 0