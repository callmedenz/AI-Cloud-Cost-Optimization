from __future__ import annotations

import json
from urllib import error, parse, request


class AlertDeliveryError(RuntimeError):
    pass


def _validate_webhook(provider: str, webhook_url: str) -> None:
    parsed = parse.urlparse(webhook_url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Webhook URL must use HTTPS")

    hostname = parsed.hostname.lower()
    if provider == "slack" and hostname != "hooks.slack.com":
        raise ValueError("Slack webhook must use hooks.slack.com")
    if provider == "discord" and hostname not in {"discord.com", "discordapp.com"}:
        raise ValueError("Discord webhook must use discord.com or discordapp.com")
    if provider not in {"slack", "discord"}:
        raise ValueError("provider must be slack or discord")


def send_alert(provider: str, webhook_url: str, message: str) -> None:
    _validate_webhook(provider, webhook_url)
    payload = json.dumps({"content": message} if provider == "discord" else {"text": message})
    http_request = request.Request(
        webhook_url,
        data=payload.encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(http_request, timeout=10) as response:
            if response.status < 200 or response.status >= 300:
                raise AlertDeliveryError(f"{provider} returned HTTP {response.status}")
    except (error.HTTPError, error.URLError, TimeoutError) as exc:
        raise AlertDeliveryError(f"{provider} webhook delivery failed") from exc
