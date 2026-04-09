"""Tests for backend.bot.notification_router."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.bot.notification_router import (
    EventType,
    NotificationChannel,
    NotificationConfig,
    NotificationRouter,
)


@pytest.fixture()
def router():
    """NotificationRouter with no default channels (no token set in test env)."""
    r = NotificationRouter()
    r._channels.clear()  # remove any auto-registered channels
    return r


# ---------------------------------------------------------------------------
# 1. Event reaches the correct channel
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_route_to_matching_channel(router):
    """An event sent to a matching channel calls the send method."""
    discord_config = NotificationConfig(
        channel=NotificationChannel.DISCORD,
        enabled=True,
        event_types=[EventType.TRADE_EXECUTED],
        webhook_url="https://discord.example.com/webhook",
    )
    router.register_channel(discord_config)

    with patch.object(router, "_send_discord", new_callable=AsyncMock) as mock_discord:
        await router.notify(EventType.TRADE_EXECUTED, "Trade executed", {})
        mock_discord.assert_awaited_once_with(
            "https://discord.example.com/webhook", "Trade executed"
        )


# ---------------------------------------------------------------------------
# 2. Disabled channel is never called
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_disabled_channel_skipped(router):
    """A disabled channel config must not be called even if event type matches."""
    config = NotificationConfig(
        channel=NotificationChannel.DISCORD,
        enabled=False,
        event_types=[],  # all events
        webhook_url="https://discord.example.com/webhook",
    )
    router.register_channel(config)

    with patch.object(router, "_send_discord", new_callable=AsyncMock) as mock_discord:
        await router.notify(EventType.ERROR, "Something broke", {})
        mock_discord.assert_not_awaited()


# ---------------------------------------------------------------------------
# 3. Discord webhook POST is called with correct payload
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_discord_webhook_called(router):
    """_send_discord posts JSON payload to the webhook URL via httpx."""
    webhook_url = "https://discord.example.com/hook123"
    message = "Whale trade detected!"

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("backend.bot.notification_router.httpx.AsyncClient", return_value=mock_client):
        await router._send_discord(webhook_url, message)

    mock_client.post.assert_awaited_once_with(webhook_url, json={"content": message})
    mock_response.raise_for_status.assert_called_once()
