"""
Strategy Registry for PolyEdge.

Central registry mapping strategy names to their classes.
Strategies self-register via BaseStrategy.__init_subclass__.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Maps strategy name -> strategy class
STRATEGY_REGISTRY: dict[str, type] = {}


def _auto_register(cls) -> None:
    """Register a BaseStrategy subclass by its `name` attribute."""
    name = getattr(cls, "name", None)
    if name and name not in STRATEGY_REGISTRY:
        STRATEGY_REGISTRY[name] = cls


class BaseStrategy:
    """Base class for all PolyEdge trading strategies.

    Subclasses must define a `name` class attribute.
    They are auto-registered in STRATEGY_REGISTRY on class creation.
    """

    name: str = ""
    description: str = ""
    category: str = "general"
    default_params: dict = {}

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        _auto_register(cls)


@dataclass
class StrategyMeta:
    """Metadata describing a registered strategy."""

    name: str
    description: str
    category: str
    default_params: dict
    enabled: bool = False  # filled from DB at query time by the API layer


def create_strategy(name: str, **kwargs) -> BaseStrategy:
    """Instantiate a registered strategy by name.

    Raises KeyError with a helpful message if the strategy is not found.
    """
    if name not in STRATEGY_REGISTRY:
        available = ", ".join(sorted(STRATEGY_REGISTRY.keys())) or "(none loaded)"
        raise KeyError(
            f"Strategy '{name}' not found in registry. "
            f"Available strategies: {available}"
        )
    cls = STRATEGY_REGISTRY[name]
    return cls(**kwargs)


def list_strategies() -> list[StrategyMeta]:
    """Return StrategyMeta for every registered strategy.

    The `enabled` field defaults to False; the API layer fills it from DB.
    """
    result = []
    for strategy_name, cls in STRATEGY_REGISTRY.items():
        result.append(
            StrategyMeta(
                name=strategy_name,
                description=getattr(cls, "description", ""),
                category=getattr(cls, "category", "general"),
                default_params=dict(getattr(cls, "default_params", {})),
                enabled=False,
            )
        )
    return result


def load_all_strategies() -> None:
    """Import all strategy modules to trigger auto-registration."""
    import importlib

    strategy_modules = [
        "backend.strategies.copy_trader",
        "backend.strategies.weather_emos",
        "backend.strategies.kalshi_arb",
        "backend.strategies.btc_oracle",
        "backend.strategies.btc_momentum",
        "backend.strategies.realtime_scanner",
        "backend.strategies.whale_pnl_tracker",
        "backend.strategies.market_maker",
    ]
    for module in strategy_modules:
        try:
            importlib.import_module(module)
        except ImportError as e:
            logging.getLogger(__name__).warning(
                f"Could not load strategy module {module}: {e}"
            )
