"""Evaluator that computes accuracy, log-loss, and calibration ECE.

Replaces the original NotImplementedError stub with a working metrics
implementation suitable for the logistic-regression baseline trained by
``model_trainer.ModelTrainer``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class EvalResult:
    accuracy: float
    log_loss: float
    brier: float
    ece: float
    n: int


class ModelEvaluator:
    """Compute headline metrics from (predicted_prob, true_label) pairs."""

    def evaluate(self, predictions: List[Tuple[float, float]]) -> Dict[str, float]:
        result = self.evaluate_full(predictions)
        return {
            "accuracy": result.accuracy,
            "log_loss": result.log_loss,
            "brier": result.brier,
            "ece": result.ece,
            "n": result.n,
        }

    def evaluate_full(self, predictions: List[Tuple[float, float]]) -> EvalResult:
        if not predictions:
            return EvalResult(0.0, 0.0, 0.0, 0.0, 0)

        n = len(predictions)
        correct = 0
        ll_sum = 0.0
        brier_sum = 0.0

        for prob, label in predictions:
            prob = max(min(float(prob), 1.0 - 1e-9), 1e-9)
            label = float(label)
            pred_class = 1.0 if prob >= 0.5 else 0.0
            if pred_class == label:
                correct += 1
            ll_sum += -(label * math.log(prob) + (1.0 - label) * math.log(1.0 - prob))
            brier_sum += (prob - label) ** 2

        accuracy = correct / n
        log_loss = ll_sum / n
        brier = brier_sum / n
        ece = self._expected_calibration_error(predictions)

        return EvalResult(
            accuracy=round(accuracy, 4),
            log_loss=round(log_loss, 4),
            brier=round(brier, 4),
            ece=round(ece, 4),
            n=n,
        )

    @staticmethod
    def _expected_calibration_error(
        predictions: List[Tuple[float, float]], bins: int = 10
    ) -> float:
        """ECE — average gap between predicted prob and empirical accuracy per bin."""
        bin_total = [0] * bins
        bin_correct = [0] * bins
        bin_conf_sum = [0.0] * bins
        for prob, label in predictions:
            idx = min(bins - 1, int(float(prob) * bins))
            bin_total[idx] += 1
            bin_correct[idx] += 1 if (float(prob) >= 0.5) == bool(label) else 0
            bin_conf_sum[idx] += float(prob)

        n = len(predictions)
        ece = 0.0
        for i in range(bins):
            if bin_total[i] == 0:
                continue
            acc = bin_correct[i] / bin_total[i]
            conf = bin_conf_sum[i] / bin_total[i]
            ece += (bin_total[i] / n) * abs(acc - conf)
        return ece
