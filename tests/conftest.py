"""Shared pytest fixtures for PolyEdge tests."""

import pytest


@pytest.fixture
def sample_ensemble_members():
    """31-member GEFS ensemble data for NYC on a warm day (~78F mean)."""
    import random

    random.seed(42)
    return [random.gauss(78.0, 3.0) for _ in range(31)]


@pytest.fixture
def sample_cold_ensemble():
    """31-member ensemble for a cold day (~45F mean)."""
    import random

    random.seed(7)
    return [random.gauss(45.0, 4.0) for _ in range(31)]
