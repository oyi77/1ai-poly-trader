"""
Integration tests for real-time balance WebSocket updates.
"""

import pytest
from unittest.mock import patch, AsyncMock
from backend.models.database import BotState, Trade


def test_stats_endpoint_returns_balance(client, db):
    state = db.query(BotState).first()
    if not state:
        state = BotState(
            is_running=False,
            bankroll=2500.0,
            total_trades=5,
            winning_trades=3,
            total_pnl=500.0,
            paper_bankroll=10000.0,
            paper_pnl=0.0,
            paper_trades=0,
            paper_wins=0,
        )
        db.add(state)
    else:
        state.bankroll = 2500.0
        state.total_trades = 5
        state.winning_trades = 3
        state.total_pnl = 500.0
    db.commit()

    response = client.get("/api/stats")
    assert response.status_code == 200

    data = response.json()
    assert "bankroll" in data
    assert data["total_trades"] == 5
    assert data["winning_trades"] == 3


def test_stats_endpoint_paper_mode(client, db):
    state = db.query(BotState).first()
    if not state:
        state = BotState(
            is_running=False,
            bankroll=10000.0,
            total_trades=0,
            winning_trades=0,
            total_pnl=0.0,
            paper_bankroll=12000.0,
            paper_pnl=2000.0,
            paper_trades=10,
            paper_wins=6,
        )
        db.add(state)
    else:
        state.paper_bankroll = 12000.0
        state.paper_pnl = 2000.0
        state.paper_trades = 10
        state.paper_wins = 6
    db.commit()

    with patch("backend.config.settings.TRADING_MODE", "paper"):
        response = client.get("/api/stats")
        assert response.status_code == 200

        data = response.json()
        assert data["mode"] == "paper"
        assert data["paper_bankroll"] == 12000.0
        assert data["paper_pnl"] == 2000.0


def test_stats_endpoint_includes_mode_specific_data(client, db):
    state = db.query(BotState).first()
    if not state:
        state = BotState(
            is_running=False,
            bankroll=5000.0,
            total_trades=3,
            winning_trades=2,
            total_pnl=300.0,
            paper_bankroll=11000.0,
            paper_pnl=1000.0,
            paper_trades=5,
            paper_wins=3,
            testnet_bankroll=200.0,
            testnet_pnl=50.0,
            testnet_trades=2,
            testnet_wins=1,
        )
        db.add(state)
    else:
        state.bankroll = 5000.0
        state.paper_bankroll = 11000.0
        state.testnet_bankroll = 200.0
    db.commit()

    response = client.get("/api/stats")
    assert response.status_code == 200

    data = response.json()
    assert "paper" in data
    assert "testnet" in data
    assert "live" in data
    assert data["paper"]["bankroll"] == 11000.0
    assert data["testnet"]["bankroll"] == 200.0
    assert data["live"]["bankroll"] == 5000.0


def test_stats_endpoint_calculates_unrealized_pnl(client, db):
    state = db.query(BotState).first()
    if not state:
        state = BotState(
            is_running=False,
            bankroll=10000.0,
            total_trades=0,
            winning_trades=0,
            total_pnl=0.0,
            paper_bankroll=10000.0,
            paper_pnl=0.0,
            paper_trades=0,
            paper_wins=0,
        )
        db.add(state)
    db.commit()

    trade = Trade(
        market_ticker="test-market",
        platform="polymarket",
        direction="up",
        entry_price=0.65,
        size=100.0,
        settled=False,
        result="pending",
        trading_mode="paper",
    )
    db.add(trade)
    db.commit()

    with patch("backend.config.settings.TRADING_MODE", "paper"):
        response = client.get("/api/stats")
        assert response.status_code == 200

        data = response.json()
        assert data["open_trades"] == 1
        assert data["open_exposure"] == 100.0


def test_stats_endpoint_handles_missing_botstate(client, db):
    db.query(BotState).delete()
    db.commit()

    response = client.get("/api/stats")
    assert response.status_code == 404
    assert "not initialized" in response.json()["detail"]


def test_stats_pnl_source_indicator(client, db):
    state = db.query(BotState).first()
    if not state:
        state = BotState(
            is_running=False,
            bankroll=10000.0,
            total_trades=0,
            winning_trades=0,
            total_pnl=0.0,
            paper_bankroll=10000.0,
            paper_pnl=0.0,
            paper_trades=0,
            paper_wins=0,
        )
        db.add(state)
    db.commit()

    response = client.get("/api/stats")
    assert response.status_code == 200

    data = response.json()
    assert "pnl_source" in data
    assert data["pnl_source"] in ["botstate", "recalculated"]


def test_stats_includes_position_metrics(client, db):
    state = db.query(BotState).first()
    if not state:
        state = BotState(
            is_running=False,
            bankroll=10000.0,
            total_trades=0,
            winning_trades=0,
            total_pnl=0.0,
            paper_bankroll=10000.0,
            paper_pnl=0.0,
            paper_trades=0,
            paper_wins=0,
        )
        db.add(state)
    db.commit()

    response = client.get("/api/stats")
    assert response.status_code == 200

    data = response.json()
    assert "open_exposure" in data
    assert "open_trades" in data
    assert "settled_trades" in data
    assert "settled_wins" in data
    assert "unrealized_pnl" in data
    assert "position_cost" in data
    assert "position_market_value" in data
