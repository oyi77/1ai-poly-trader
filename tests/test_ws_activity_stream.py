import pytest
import asyncio
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocket
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from backend.api.main import app
from backend.websockets.activity_stream import ActivityConnectionManager, broadcast_activity


@pytest.fixture
def mock_websocket():
    ws = AsyncMock(spec=WebSocket)
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    return ws


@pytest.mark.asyncio
async def test_connection_manager_connect(mock_websocket):
    manager = ActivityConnectionManager()
    
    await manager.connect(mock_websocket)
    
    assert mock_websocket in manager.active_connections
    assert len(manager.active_connections) == 1
    mock_websocket.accept.assert_called_once()


@pytest.mark.asyncio
async def test_connection_manager_disconnect(mock_websocket):
    manager = ActivityConnectionManager()
    
    await manager.connect(mock_websocket)
    await manager.disconnect(mock_websocket)
    
    assert mock_websocket not in manager.active_connections
    assert len(manager.active_connections) == 0


@pytest.mark.asyncio
async def test_connection_manager_broadcast_single_client(mock_websocket):
    manager = ActivityConnectionManager()
    await manager.connect(mock_websocket)
    
    message = {
        "strategy_name": "btc_momentum",
        "decision_type": "entry",
        "confidence_score": 0.85
    }
    
    await manager.broadcast(message)
    await asyncio.sleep(0.1)
    
    mock_websocket.send_json.assert_called_once_with(message)


@pytest.mark.asyncio
async def test_connection_manager_broadcast_multiple_clients():
    manager = ActivityConnectionManager()
    
    ws1 = AsyncMock(spec=WebSocket)
    ws1.accept = AsyncMock()
    ws1.send_json = AsyncMock()
    
    ws2 = AsyncMock(spec=WebSocket)
    ws2.accept = AsyncMock()
    ws2.send_json = AsyncMock()
    
    await manager.connect(ws1)
    await manager.connect(ws2)
    
    message = {"test": "data"}
    await manager.broadcast(message)
    await asyncio.sleep(0.1)
    
    ws1.send_json.assert_called_once_with(message)
    ws2.send_json.assert_called_once_with(message)


@pytest.mark.asyncio
async def test_connection_manager_broadcast_removes_stale_connection():
    manager = ActivityConnectionManager()
    
    ws_good = AsyncMock(spec=WebSocket)
    ws_good.accept = AsyncMock()
    ws_good.send_json = AsyncMock()
    
    ws_bad = AsyncMock(spec=WebSocket)
    ws_bad.accept = AsyncMock()
    ws_bad.send_json = AsyncMock(side_effect=Exception("Connection closed"))
    
    await manager.connect(ws_good)
    await manager.connect(ws_bad)
    
    assert len(manager.active_connections) == 2
    
    await manager.broadcast({"test": "data"})
    await asyncio.sleep(0.1)
    
    assert ws_good in manager.active_connections
    assert ws_bad not in manager.active_connections
    assert len(manager.active_connections) == 1


@pytest.mark.asyncio
async def test_connection_manager_broadcast_no_clients():
    manager = ActivityConnectionManager()
    
    await manager.broadcast({"test": "data"})


@pytest.mark.asyncio
async def test_broadcast_activity_adds_metadata():
    manager = ActivityConnectionManager()
    
    ws = AsyncMock(spec=WebSocket)
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    
    await manager.connect(ws)
    
    with patch('backend.websockets.activity_stream.activity_manager', manager):
        activity_data = {
            "strategy_name": "btc_oracle",
            "decision_type": "exit",
            "confidence_score": 0.92,
            "mode": "paper"
        }
        
        await broadcast_activity(activity_data)
        await asyncio.sleep(0.2)
        
        assert ws.send_json.called
        call_args = ws.send_json.call_args[0][0]
        assert call_args["type"] == "activity_update"
        assert "timestamp" in call_args
        assert call_args["strategy_name"] == "btc_oracle"
        assert call_args["decision_type"] == "exit"


@pytest.mark.asyncio
async def test_broadcast_activity_non_blocking():
    manager = ActivityConnectionManager()
    
    ws = AsyncMock(spec=WebSocket)
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    
    await manager.connect(ws)
    
    with patch('backend.websockets.activity_stream.activity_manager', manager):
        start = asyncio.get_event_loop().time()
        
        await broadcast_activity({"strategy_name": "test", "decision_type": "hold", "confidence_score": 0.5})
        
        elapsed = asyncio.get_event_loop().time() - start
        
        assert elapsed < 0.05


@pytest.mark.asyncio
async def test_broadcast_activity_integration():
    manager = ActivityConnectionManager()
    
    ws = AsyncMock(spec=WebSocket)
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    
    await manager.connect(ws)
    
    with patch('backend.websockets.activity_stream.activity_manager', manager):
        activity_data = {
            "strategy_name": "btc_momentum",
            "decision_type": "entry",
            "confidence_score": 0.75,
            "mode": "paper",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        await broadcast_activity(activity_data)
        await asyncio.sleep(0.3)
        
        assert ws.send_json.called
        call_args = ws.send_json.call_args[0][0]
        assert call_args["type"] == "activity_update"
        assert call_args["strategy_name"] == "btc_momentum"
