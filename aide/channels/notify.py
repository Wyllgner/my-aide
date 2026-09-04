"""Como o assessor alcança você. Hoje: terminal e notificação de desktop."""

from __future__ import annotations

import logging
import shutil
import subprocess
from abc import ABC, abstractmethod

log = logging.getLogger(__name__)

URGENCY = {1: "critical", 2: "normal", 3: "low", 4: "low"}


class Notifier(ABC):
    @abstractmethod
    def send(self, title: str, body: str, urgency: str = "normal") -> bool:
        """True se a mensagem saiu."""


class ConsoleNotifier(Notifier):
    def send(self, title: str, body: str, urgency: str = "normal") -> bool:
        print(f"\n── {title} ──\n{body}\n")
        return True


class DesktopNotifier(Notifier):
    """notify-send no Linux. Cai para o console se não existir."""

    def __init__(self, fallback: Notifier | None = None):
        self.binary = shutil.which("notify-send")
        self.fallback = fallback or ConsoleNotifier()

    def send(self, title: str, body: str, urgency: str = "normal") -> bool:
        if not self.binary:
            return self.fallback.send(title, body, urgency)
        try:
            subprocess.run(
                [self.binary, "--app-name=my-aide", f"--urgency={urgency}", title, body],
                check=True, timeout=10,
            )
            return True
        except (subprocess.SubprocessError, OSError) as exc:
            log.warning("notify-send falhou (%s); caindo para o console", exc)
            return self.fallback.send(title, body, urgency)


class MultiNotifier(Notifier):
    """Manda por todos os canais; basta um funcionar."""

    def __init__(self, *channels: Notifier):
        self.channels = channels

    def send(self, title: str, body: str, urgency: str = "normal") -> bool:
        # a lista é proposital: com gerador, any() pararia no primeiro canal
        # que desse certo e os outros nunca receberiam a mensagem.
        return any([c.send(title, body, urgency) for c in self.channels])  # noqa: C419


def build_notifier(config) -> Notifier:
    channels = getattr(config, "notify_channels", ("desktop",))
    built: list[Notifier] = []
    for name in channels:
        if name == "desktop":
            built.append(DesktopNotifier())
        elif name == "console":
            built.append(ConsoleNotifier())
        elif name == "telegram":
            telegram = _build_telegram(config)
            if telegram:
                built.append(telegram)
        else:
            log.warning("canal de notificação desconhecido: %s", name)
    return MultiNotifier(*built) if built else ConsoleNotifier()


def _build_telegram(config) -> Notifier | None:
    cfg = getattr(config, "telegram", None)
    if cfg is None or not cfg.usable:
        log.warning(
            "canal telegram pedido mas não configurado "
            "(precisa de enabled, TELEGRAM_BOT_TOKEN e allowed_chat_ids)"
        )
        return None

    from aide.channels.telegram import TelegramClient, TelegramNotifier

    client = TelegramClient(cfg.token)
    return TelegramNotifier(client, cfg.allowed_chat_ids[0])
