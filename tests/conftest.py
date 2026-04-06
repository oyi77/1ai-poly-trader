"""Shared pytest fixtures for PolyEdge tests."""
import pytest
import asyncio


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_ensemble_members():
    """31-member GEFS ensemble data for NYC on a warm day (~78F mean)."""
    import random
    random.seed(42)
    # Mean ~78F, std ~3F — simulates a summer day
    return [random.gauss(78.0, 3.0) for _ in range(31)]


@pytest.fixture
def sample_cold_ensemble():
    """31-member ensemble for a cold day (~45F mean)."""
    import random
    random.seed(7)
    return [random.gauss(45.0, 4.0) for _ in range(31)]
