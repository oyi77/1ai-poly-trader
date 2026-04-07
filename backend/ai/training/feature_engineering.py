"""Feature engineering for the prediction model.

Transforms raw Polymarket market dicts into the canonical feature dict
that ``PredictionEngine.predict`` consumes. Phase 4 milestone — replaces
the original NotImplementedError stub with a working transform that
mirrors ``PredictionEngine.extract_features``.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List


# Canonical feature order — kept stable so trained model coefficients align.
FEATURE_ORDER: List[str] = [
    "edge",
    "model_probability",
    "market_probability",
    "whale_pressure",
    "sentiment",
    "volume_log",
]


class FeatureEngineer:
    """Stateless transformer from raw market rows to canonical features."""

    def transform(self, raw: List[Dict[str, Any]]) -> List[Dict[str, float]]:
        return [self.transform_one(row) for row in raw]

    def transform_one(self, row: Dict[str, Any]) -> Dict[str, float]:
        yes_price = float(row.get("yes_price", row.get("yesPrice", 0.5)) or 0.5)
        volume = float(row.get("volume", 0.0) or 0.0)
        liquidity = float(row.get("liquidity", 0.0) or 0.0)
        whale_pressure = float(row.get("whale_pressure", 0.0) or 0.0)
        sentiment = float(row.get("sentiment", 0.0) or 0.0)

        # Use yes_price as both market_probability and a soft model prior.
        model_probability = float(row.get("model_probability", yes_price) or yes_price)
        edge = model_probability - yes_price

        return {
            "edge": edge,
            "model_probability": model_probability,
            "market_probability": yes_price,
            "whale_pressure": whale_pressure,
            "sentiment": sentiment,
            "volume_log": math.log1p(max(volume + liquidity * 0.1, 0.0)),
        }

    def to_vector(self, features: Dict[str, float]) -> List[float]:
        return [features.get(k, 0.0) for k in FEATURE_ORDER]
