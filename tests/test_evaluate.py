"""Unit tests for metric, threshold and risk-tier helpers."""
import numpy as np
import pytest

from src.models import evaluate


def test_threshold_metrics_confusion_matrix():
    y = np.array([1, 1, 0, 0, 1, 0])
    p = np.array([0.9, 0.4, 0.8, 0.1, 0.7, 0.2])
    m = evaluate.threshold_metrics(y, p, 0.5)
    assert m["confusion_matrix"] == {"tn": 2, "fp": 1, "fn": 1, "tp": 2}
    assert m["precision"] == pytest.approx(2 / 3)
    assert m["recall"] == pytest.approx(2 / 3)
    assert m["f1"] == pytest.approx(2 / 3)


def test_top_k_metrics_and_capacity_cutoff():
    y = np.array([1] * 5 + [0] * 95)
    p = np.linspace(1, 0, 100)                 # perfect ranking
    m = evaluate.ranking_metrics(y, p)
    assert m["precision_top5"] == 1.0 and m["recall_top5"] == 1.0
    assert m["precision_top10"] == 0.5 and m["recall_top10"] == 1.0
    assert evaluate.capacity_cutoff(p, 0.10) == pytest.approx(p[9])


def test_risk_levels_are_ordered_by_cutoffs():
    cut = {"Critical": 0.6, "High": 0.4, "Medium": 0.2}
    levels = evaluate.assign_risk_level(np.array([0.7, 0.6, 0.45, 0.2, 0.19]), cut)
    assert list(levels) == ["Critical", "Critical", "High", "Medium", "Low"]


def test_invalid_probabilities_rejected():
    with pytest.raises(ValueError):
        evaluate.ranking_metrics(np.array([0, 1]), np.array([0.2, 1.4]))

