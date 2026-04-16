"""Research data models for the PolyEdge research pipeline."""

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class ResearchItem:
    title: str
    source: str
    content: str  # summary/excerpt only (max 500 chars)
    relevance_score: float
    url: str
    fingerprint: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    id: int = None  # set after DB storage
