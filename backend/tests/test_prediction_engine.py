from backend.ai.prediction_engine import PredictionEngine, Prediction


def _baseline_engine() -> PredictionEngine:
    """Return engine using deterministic baseline weights (no trained model)."""
    return PredictionEngine(model_path="/nonexistent/model.pkl")


def test_prediction_returns_valid_range():
    e = _baseline_engine()
    f = e.extract_features(
        {"volume": 100000},
        {"edge": 0.05, "model_probability": 0.7, "market_probability": 0.5},
    )
    p = e.predict(f)
    assert isinstance(p, Prediction)
    assert 0.0 <= p.probability_yes <= 1.0
    assert 0.0 <= p.confidence <= 1.0
    assert p.model_version == "baseline-0.1"


def test_strong_positive_signal_high_prob():
    e = _baseline_engine()
    f = e.extract_features(
        {"volume": 1000000},
        {
            "edge": 0.2,
            "model_probability": 0.9,
            "market_probability": 0.5,
            "whale_pressure": 1.0,
            "sentiment": 0.5,
        },
    )
    p = e.predict(f)
    assert p.probability_yes > 0.7


def test_strong_negative_signal_low_prob():
    e = _baseline_engine()
    f = e.extract_features(
        {"volume": 1000000},
        {
            "edge": -0.2,
            "model_probability": 0.1,
            "market_probability": 0.9,
            "whale_pressure": -1.0,
            "sentiment": -0.5,
        },
    )
    p = e.predict(f)
    assert p.probability_yes < 0.3


def test_zero_features_neutral():
    e = _baseline_engine()
    p = e.predict(
        {
            k: 0.0
            for k in [
                "edge",
                "model_probability",
                "market_probability",
                "whale_pressure",
                "sentiment",
                "volume_log",
            ]
        }
    )
    assert abs(p.probability_yes - 0.5) < 1e-6


def test_trained_model_loads_and_returns_valid_range():
    """When a trained model exists on disk, verify it returns valid probabilities."""
    e = PredictionEngine()  # uses default model path
    f = e.extract_features(
        {"volume": 100000},
        {"edge": 0.05, "model_probability": 0.7, "market_probability": 0.5},
    )
    p = e.predict(f)
    assert isinstance(p, Prediction)
    assert 0.0 <= p.probability_yes <= 1.0
    assert 0.0 <= p.confidence <= 1.0
