"""API tests for /api/v1/meteora/* endpoints — respx-mocked, admin-authed.

Auth follows the repo-wide require_admin convention: every request must carry
`Authorization: Bearer <ADMIN_API_KEY>`; unauthenticated calls get 401/403.
"""
import json
from pathlib import Path

import pytest
import respx

from backend.config import settings

FIXTURES = Path(__file__).parent / "fixtures" / "meteora"
DISCOVERY_BASE = "https://pool-discovery-api.datapi.meteora.ag"

_TEST_ADMIN_KEY = "meteora-test-key"


def _fixture_pools():
    data = json.loads((FIXTURES / "discovery_pools_trending_30m.json").read_text())
    return data.get("data") or []


@pytest.fixture(autouse=True)
def _admin_key():
    original = settings.ADMIN_API_KEY
    settings.ADMIN_API_KEY = _TEST_ADMIN_KEY
    yield
    settings.ADMIN_API_KEY = original


@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {_TEST_ADMIN_KEY}"}


# ---------------------------------------------------------------------------
# Auth enforcement


def test_unauthenticated_candidates_rejected(client):
    resp = client.get("/api/v1/meteora/candidates")
    assert resp.status_code in (401, 403)


def test_wrong_bearer_rejected(client):
    resp = client.get(
        "/api/v1/meteora/candidates",
        headers={"Authorization": "Bearer wrong"},
    )
    assert resp.status_code == 401


def test_unauthenticated_screen_rejected(client):
    assert client.post("/api/v1/meteora/screen").status_code in (401, 403)


# ---------------------------------------------------------------------------
# Authenticated flows


def test_candidates_empty_initially(client, auth_headers):
    resp = client.get("/api/v1/meteora/candidates", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_cycles_latest_none_initially(client, auth_headers):
    resp = client.get("/api/v1/meteora/cycles/latest", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() is None


@respx.mock
def test_screen_cycle_persists_and_serves(client, auth_headers):
    pools = _fixture_pools()
    respx.get(f"{DISCOVERY_BASE}/pools").respond(json={"data": pools})

    resp = client.post(
        "/api/v1/meteora/screen?timeframe=30m&category=trending&page_size=25",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["screened"] == len(pools)
    assert body["accepted"] + body["rejected"] == len(pools)
    scores = [t["degen_score"] for t in body["top"]]
    assert scores == sorted(scores, reverse=True)

    served = client.get(
        "/api/v1/meteora/candidates?limit=200", headers=auth_headers
    ).json()
    assert len(served) == body["accepted"]

    latest = client.get("/api/v1/meteora/cycles/latest", headers=auth_headers).json()
    assert latest is not None
    assert latest["cycle_id"] == body["cycle_id"]
    assert latest["screened"] == len(pools)


@respx.mock
def test_screen_rejects_invalid_timeframe(client, auth_headers):
    resp = client.post(
        "/api/v1/meteora/screen?timeframe=7x", headers=auth_headers
    )
    assert resp.status_code == 422


@respx.mock
def test_cycle_detail_endpoint(client, auth_headers):
    respx.get(f"{DISCOVERY_BASE}/pools").respond(json={"data": _fixture_pools()})
    created = client.post(
        "/api/v1/meteora/screen?page_size=5", headers=auth_headers
    ).json()
    detail = client.get(
        f"/api/v1/meteora/candidates/{created['cycle_id']}?limit=500",
        headers=auth_headers,
    )
    assert detail.status_code == 200
    assert len(detail.json()) == created["screened"]
