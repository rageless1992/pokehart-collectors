"""Send alerts to the desktop and/or a Discord webhook."""

import logging

import requests

log = logging.getLogger(__name__)


class Notifier:
    def __init__(self, alerts_cfg: dict):
        self.cfg = alerts_cfg or {}

    def send(self, title: str, message: str, url: str = "") -> None:
        if self.cfg.get("desktop", True):
            self._desktop(title, message)
        webhook = self.cfg.get("discord_webhook")
        if webhook:
            self._discord(webhook, title, message, url)
        log.info("ALERT: %s | %s | %s", title, message, url)

    def _desktop(self, title: str, message: str) -> None:
        try:
            from plyer import notification
            notification.notify(title=title, message=message, app_name="Pokemon Tracker", timeout=15)
        except Exception as e:  # plyer backend missing, headless, etc.
            log.warning("desktop notification failed (%s)", e)

    def _discord(self, webhook: str, title: str, message: str, url: str) -> None:
        content = f"**{title}**\n{message}"
        if url:
            content += f"\n{url}"
        try:
            requests.post(webhook, json={"content": content}, timeout=10)
        except Exception as e:
            log.warning("discord notification failed (%s)", e)
