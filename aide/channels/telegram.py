"""Telegram: o canal que alcança você no celular sem abrir nada.

Bot API direto por HTTP. Sem dependência nova de propósito — a superfície que
usamos é pequena (getUpdates, sendMessage) e uma lib traria um loop de eventos
próprio para dentro do daemon.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from aide.channels.notify import Notifier

log = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/{method}"
LIMITE_MENSAGEM = 4096
TENTATIVAS_REDE = 3


class TelegramError(RuntimeError):
    pass


class TelegramClient:
    def __init__(self, token: str, timeout: int = 15):
        if not token:
            raise ValueError("token do Telegram vazio")
        self.token = token
        self.timeout = timeout

    def call(self, method: str, params: dict[str, Any] | None = None,
             timeout: int | None = None, tentativas: int = TENTATIVAS_REDE) -> Any:
        """Chama a Bot API.

        Falha de rede é passageira e sem retry come a resposta em silêncio — o
        usuário manda mensagem e o bot simplesmente não responde. Erro HTTP não
        é reenviado: 409 e 400 não melhoram na segunda tentativa.
        """
        url = API.format(token=self.token, method=method)
        corpo = json.dumps(params or {}).encode()
        ultima: Exception | None = None

        for tentativa in range(1, tentativas + 1):
            req = urllib.request.Request(
                url, data=corpo, headers={"Content-Type": "application/json"}
            )
            try:
                with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                    payload = json.loads(resp.read())
            except urllib.error.HTTPError as exc:
                detalhe = exc.read().decode(errors="replace")[:200]
                raise TelegramError(f"{method} falhou ({exc.code}): {detalhe}") from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                ultima = exc
                if tentativa < tentativas:
                    espera = 2 ** (tentativa - 1)
                    log.warning("%s falhou (%s); tentativa %s em %ss",
                                method, exc, tentativa + 1, espera)
                    time.sleep(espera)
                continue

            if not payload.get("ok"):
                raise TelegramError(f"{method} recusado: {payload.get('description')}")
            return payload.get("result")

        raise TelegramError(f"{method} não completou: {ultima}")

    def me(self) -> dict:
        return self.call("getMe")

    def send_message(self, chat_id: int | str, text: str, markdown: bool = False) -> dict:
        # o Telegram corta em 4096; melhor cortar avisando do que perder o fim
        if len(text) > LIMITE_MENSAGEM:
            text = text[: LIMITE_MENSAGEM - 20] + "\n[...cortado]"
        payload = {"chat_id": chat_id, "text": text}
        if markdown:
            payload["parse_mode"] = "Markdown"
        return self.call("sendMessage", payload)

    def send_action(self, chat_id: int | str, action: str = "typing") -> None:
        """Mostra "digitando…" no chat. Dura cinco segundos, então precisa ser
        repetido enquanto o trabalho continua.

        Falha é engolida de propósito: um indicador que não apareceu é um
        detalhe, e derrubar a resposta por causa dele seria trocar o silêncio
        por um erro.
        """
        try:
            self.call("sendChatAction", {"chat_id": chat_id, "action": action},
                      tentativas=1)
        except (TelegramError, OSError):
            log.debug("sendChatAction falhou", exc_info=True)

    def get_updates(self, offset: int | None = None, timeout: int = 25) -> list[dict]:
        """Long polling: a chamada fica aberta até chegar mensagem ou estourar."""
        params: dict[str, Any] = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        return self.call("getUpdates", params, timeout=timeout + 10) or []


class TelegramNotifier(Notifier):
    """Manda os avisos do scheduler para o seu chat."""

    def __init__(self, client: TelegramClient, chat_id: int | str):
        self.client = client
        self.chat_id = chat_id

    def send(self, title: str, body: str, urgency: str = "normal") -> bool:
        texto = f"{title}\n\n{body}" if body else title
        return self._mandar(texto)

    def enviar(self, mensagem, urgency: str = "normal") -> bool:
        from aide.channels.formato import para_telegram

        return self._mandar(para_telegram(mensagem), markdown=True)

    def _mandar(self, texto: str, markdown: bool = False) -> bool:
        try:
            self.client.send_message(self.chat_id, texto, markdown=markdown)
        except TelegramError as exc:
            log.warning("telegram não entregou: %s", exc)
            return False
        return True
