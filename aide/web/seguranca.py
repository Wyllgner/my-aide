"""A fronteira da página, conferida a cada pedido.

Escutar em 127.0.0.1 impede que outra máquina chegue aqui, mas não impede o
seu próprio navegador de ser usado contra você. Qualquer site aberto numa aba
consegue mandar o navegador pedir coisas a 127.0.0.1:8787. Três defesas, uma
por ataque:

- **Host.** Um domínio do atacante que passa a apontar para 127.0.0.1 (DNS
  rebinding) faz o navegador tratar esta página como se fosse dele, e aí ele
  lê tudo, privado inclusive. O pedido chega com o nome dele no Host; só
  127.0.0.1 e localhost passam.
- **Escrita só da própria página.** Um formulário em outro site pode postar
  aqui sem ler a resposta, e para escrever isso basta. Toda escrita precisa
  vir com o Origin desta página e com o cabeçalho `X-Aide`, que um formulário
  não sabe pôr e que um `fetch` de outra origem só põe depois de uma
  permissão (preflight) que nunca é dada.
- **Cabeçalhos.** CSP sem script de fora nem script embutido, a página não
  pode ser posta num iframe, e nada é guardado em cache em disco.
"""

from __future__ import annotations

HOSTS = frozenset({"127.0.0.1", "localhost"})
LEITURA = frozenset({"GET", "HEAD"})
CABECALHO_ESCRITA = "x-aide"

# 'unsafe-inline' só em estilo: as telas usam style="" em todo canto, e estilo
# não executa nada. Script só vem de /app.js.
DIRETIVAS = (
    "default-src 'none'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src https://fonts.gstatic.com",
    "img-src 'self' data:",
    "connect-src 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "base-uri 'none'",
)
CSP = "; ".join(DIRETIVAS)

CABECALHOS = {
    "content-security-policy": CSP,
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "cross-origin-opener-policy": "same-origin",
    "cross-origin-resource-policy": "same-origin",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
}


def nome_do_host(host: str) -> str:
    """'127.0.0.1:8787' -> '127.0.0.1'. A porta não importa: quem faz o
    rebinding controla o nome, não a porta."""
    if host.startswith("["):
        return host.split("]")[0] + "]"
    return host.rsplit(":", 1)[0] if ":" in host else host


def host_permitido(host: str | None) -> bool:
    return bool(host) and nome_do_host(host.lower()) in HOSTS


def escrita_permitida(metodo: str, host: str, origin: str | None,
                      marca: str | None, sec_fetch_site: str | None) -> str | None:
    """None se pode escrever; senão, o motivo da recusa."""
    if metodo in LEITURA:
        return None
    if marca != "1":
        return "escrita sem o cabeçalho da página"
    if origin != f"http://{host.lower()}":
        return "escrita vinda de outra origem"
    if sec_fetch_site not in (None, "same-origin"):
        return "escrita vinda de outro site"
    return None


def instalar(app) -> None:
    from fastapi.responses import PlainTextResponse

    @app.middleware("http")
    async def fronteira(request, call_next):
        host = request.headers.get("host", "")
        if not host_permitido(host):
            resposta = PlainTextResponse("host não permitido", status_code=421)
        else:
            motivo = escrita_permitida(
                request.method, host, request.headers.get("origin"),
                request.headers.get(CABECALHO_ESCRITA),
                request.headers.get("sec-fetch-site"))
            if motivo:
                resposta = PlainTextResponse(motivo, status_code=403)
            else:
                resposta = await call_next(request)
        for nome, valor in CABECALHOS.items():
            resposta.headers.setdefault(nome, valor)
        # a página mostra privado; cópia em cache de disco é cópia fora do banco
        if "cache-control" not in resposta.headers:
            resposta.headers["cache-control"] = "no-store"
        return resposta
