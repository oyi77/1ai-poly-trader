"""WebSocket streaming for real-time proposal updates.

Broadcasts proposal status changes to all connected WebSocket clients when
proposals are approved, rejected, or created.
"""

import logging
import asyncio
from typing import Set, Dict, Any
from datetime import datetime, timezone

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class ProposalConnectionManager:
    """Manages WebSocket connections for proposal streaming."""
    
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket):
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)
        logger.info(f"Proposal WebSocket connected. Total clients: {len(self.active_connections)}")
    
    async def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        async with self._lock:
            self.active_connections.discard(websocket)
        logger.info(f"Proposal WebSocket disconnected. Total clients: {len(self.active_connections)}")
    
    async def broadcast(self, message: Dict[str, Any]):
        """Broadcast a message to all connected clients."""
        if not self.active_connections:
            logger.debug("No active connections to broadcast to")
            return
        
        logger.debug(f"Broadcasting proposal update to {len(self.active_connections)} clients")
        
        connections = list(self.active_connections)
        
        tasks = []
        for connection in connections:
            task = asyncio.create_task(self._send_to_client(connection, message))
            tasks.append(task)
        
        if tasks:
            await asyncio.wait(tasks, timeout=1.0)
    
    async def _send_to_client(self, websocket: WebSocket, message: Dict[str, Any]):
        """Send message to a single client, handling errors gracefully."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.warning(f"Failed to send to client: {e}")
            await self.disconnect(websocket)


proposal_manager = ProposalConnectionManager()


async def broadcast_proposal_update(proposal_data: Dict[str, Any]):
    """Broadcast a proposal update to all connected WebSocket clients.
    
    Args:
        proposal_data: Proposal data with keys:
            - id: int
            - strategy_name: str
            - admin_decision: str
            - admin_user_id: str (optional)
            - timestamp: str (ISO format)
    """
    message = {
        "type": "proposal_update",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **proposal_data
    }
    
    asyncio.create_task(proposal_manager.broadcast(message))
    logger.debug(f"Queued proposal broadcast: {proposal_data.get('strategy_name')} - {proposal_data.get('admin_decision')}")
