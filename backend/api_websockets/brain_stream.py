"""WebSocket streaming for Brain Graph real-time updates.

Broadcasts events when:
- New signal arrives (strategy execution)
- Debate starts/ends (Bull/Bear/Judge)
- Trade executed
- Proposal generated
"""

import logging
import asyncio
from typing import Set, Dict, Any
from datetime import datetime, timezone

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class BrainConnectionManager:
    """Manages WebSocket connections for brain graph streaming."""
    
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)
        logger.info(f"Brain WebSocket connected. Total clients: {len(self.active_connections)}")
    
    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            self.active_connections.discard(websocket)
        logger.info(f"Brain WebSocket disconnected. Total clients: {len(self.active_connections)}")
    
    async def broadcast(self, message: Dict[str, Any]):
        if not self.active_connections:
            logger.debug("No active brain connections to broadcast to")
            return
        
        logger.debug(f"Broadcasting brain event to {len(self.active_connections)} clients")
        
        connections = list(self.active_connections)
        
        tasks = []
        for connection in connections:
            task = asyncio.create_task(self._send_to_client(connection, message))
            tasks.append(task)
        
        if tasks:
            await asyncio.wait(tasks, timeout=1.0)
    
    async def _send_to_client(self, websocket: WebSocket, message: Dict[str, Any]):
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.warning(f"Failed to send to brain client: {e}")
            await self.disconnect(websocket)


brain_manager = BrainConnectionManager()


async def broadcast_signal_received(signal_data: Dict[str, Any]):
    message = {
        "type": "signal_received",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "node": signal_data.get("source", "unknown"),
        "data": signal_data
    }
    asyncio.create_task(brain_manager.broadcast(message))
    logger.debug(f"Queued signal_received broadcast: {signal_data.get('source')}")


async def broadcast_debate_started(market_id: str, nodes: list):
    message = {
        "type": "debate_started",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "nodes": nodes,
        "market_id": market_id
    }
    asyncio.create_task(brain_manager.broadcast(message))
    logger.debug(f"Queued debate_started broadcast: {market_id}")


async def broadcast_debate_ended(market_id: str, consensus: float, confidence: float):
    message = {
        "type": "debate_ended",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "market_id": market_id,
        "consensus": consensus,
        "confidence": confidence
    }
    asyncio.create_task(brain_manager.broadcast(message))
    logger.debug(f"Queued debate_ended broadcast: {market_id}")


async def broadcast_trade_executed(trade_data: Dict[str, Any]):
    message = {
        "type": "trade_executed",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "node": "trade_executor",
        "data": trade_data
    }
    asyncio.create_task(brain_manager.broadcast(message))
    logger.debug(f"Queued trade_executed broadcast: trade_id={trade_data.get('id')}")


async def broadcast_proposal_generated(proposal_data: Dict[str, Any]):
    message = {
        "type": "proposal_generated",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "node": "proposal_generator",
        "data": proposal_data
    }
    asyncio.create_task(brain_manager.broadcast(message))
    logger.debug(f"Queued proposal_generated broadcast: {proposal_data.get('strategy_name')}")


async def broadcast_node_status_change(node_id: str, status: str):
    message = {
        "type": "node_status_change",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "node_id": node_id,
        "status": status
    }
    asyncio.create_task(brain_manager.broadcast(message))
    logger.debug(f"Queued node_status_change broadcast: {node_id} -> {status}")


async def broadcast_edge_activation(from_node: str, to_node: str, active: bool):
    message = {
        "type": "edge_activation",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "from_node": from_node,
        "to_node": to_node,
        "active": active
    }
    asyncio.create_task(brain_manager.broadcast(message))
    logger.debug(f"Queued edge_activation broadcast: {from_node} -> {to_node} (active={active})")
