"""End-to-end training entry point.

Usage::

    python -m backend.ai.training.train

Pulls resolved Polymarket markets, builds features, trains a logistic
regression baseline, evaluates with a hold-out split, and saves the
model + metadata under ``backend/ai/models/``.
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import List, Tuple

import numpy as np

from backend.ai.training.data_collector import DataCollector, TrainingExample
from backend.ai.training.feature_engineering import FeatureEngineer
from backend.ai.training.model_evaluator import ModelEvaluator
from backend.ai.training.model_trainer import ModelTrainer

logger = logging.getLogger("trading_bot.training.train")


def _split(
    examples: List[TrainingExample], holdout_frac: float = 0.2, seed: int = 42
) -> Tuple[List[TrainingExample], List[TrainingExample]]:
    rng = random.Random(seed)
    shuffled = examples[:]
    rng.shuffle(shuffled)
    cut = max(1, int(len(shuffled) * holdout_frac))
    return shuffled[cut:], shuffled[:cut]


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    collector = DataCollector(page_size=100, max_pages=10)
    examples = await collector.collect()
    logger.info(f"collected {len(examples)} labelled examples")

    if len(examples) < 16:
        logger.warning(
            f"only {len(examples)} examples; baseline requires >=16. "
            "Falling back to synthetic seed for the pipeline smoke."
        )
        examples = _synthetic_examples(64)

    train_set, eval_set = _split(examples, holdout_frac=0.2)
    trainer = ModelTrainer()
    result = trainer.train(train_set)
    trainer.write_metadata(result)

    fe = FeatureEngineer()
    import pickle
    with open(result.model_path, "rb") as fh:
        bundle = pickle.load(fh)
    model = bundle["model"]
    X_eval = np.array([fe.to_vector(ex.features) for ex in eval_set], dtype=float)
    if len(X_eval) > 0:
        probs = model.predict_proba(X_eval)[:, 1]
        pairs = list(zip(probs.tolist(), [ex.label for ex in eval_set]))
        metrics = ModelEvaluator().evaluate_full(pairs)
        logger.info(
            f"eval: acc={metrics.accuracy} log_loss={metrics.log_loss} "
            f"brier={metrics.brier} ece={metrics.ece} n={metrics.n}"
        )

    logger.info(
        f"training complete — model saved to {result.model_path} "
        f"({result.n_examples} examples, train_acc={result.train_accuracy:.3f})"
    )


def _synthetic_examples(n: int) -> List[TrainingExample]:
    rng = random.Random(0)
    fe = FeatureEngineer()
    out: List[TrainingExample] = []
    for _ in range(n):
        edge = rng.uniform(-0.2, 0.2)
        yes = rng.uniform(0.1, 0.9)
        features = {
            "edge": edge,
            "model_probability": max(0.0, min(1.0, yes + edge)),
            "market_probability": yes,
            "whale_pressure": rng.uniform(-1, 1),
            "sentiment": rng.uniform(-1, 1),
            "volume_log": rng.uniform(0, 12),
        }
        # Synthetic label: probability of YES correlated with edge + sentiment
        score = features["edge"] * 3 + features["sentiment"] * 0.5
        label = 1.0 if score + rng.uniform(-0.3, 0.3) > 0 else 0.0
        out.append(TrainingExample(features=features, label=label, market_id="syn"))
        _ = fe.to_vector(features)  # exercise the FE
    return out


if __name__ == "__main__":
    asyncio.run(main())
