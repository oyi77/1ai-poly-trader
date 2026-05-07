import pytest
from backend.services.mirofish_service import get_mirofish_service, MiroFishService

def test_get_mirofish_service_singleton():
    import backend.services.mirofish_service as m_service
    # Reset global for clean test
    m_service._service_instance = None

    # First call should create a new instance
    instance1 = get_mirofish_service()
    assert isinstance(instance1, MiroFishService)
    assert m_service._service_instance is instance1

    # Second call should return the exact same instance
    instance2 = get_mirofish_service()
    assert instance1 is instance2

    # Reset again and verify a new one is created
    m_service._service_instance = None
    instance3 = get_mirofish_service()
    assert instance3 is not instance1
    assert isinstance(instance3, MiroFishService)
