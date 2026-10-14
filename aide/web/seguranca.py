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

import re

HOSTS = frozenset({"127.0.0.1", "localhost"})
LEITURA = frozenset({"GET", "HEAD"})
CABECALHO_ESCRITA = "x-aide"

# 'unsafe-inline' só em estilo: as telas usam style="" em todo canto, e estilo
# não executa nada. Script só vem de /app.js.
DIRETIVAS = (
    "default-src 'none'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "font-src 'self'",
    "img-src 'self' data:",
    "media-src 'self'",
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


# o nome e, se vier, só dígitos de porta: '127.0.0.1:8787@evil' não é host
HOST = re.compile(r"(?P<nome>[^:]+)(:\d{1,5})?")


def host_permitido(host: str | None) -> bool:
    """A porta não importa: quem faz o rebinding controla o nome, não a porta."""
    casado = HOST.fullmatch((host or "").lower())
    return bool(casado) and casado["nome"] in HOSTS


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


# a maior nota aceita (notas_api.TAMANHO_MAXIMO) mais folga para o JSON em volta
CORPO_MAXIMO = 3 * 1024 * 1024
# a rota que recebe anexo: o corpo é o arquivo, até o limite de anexos.
# Ela mesma conta os bytes enquanto grava, para o pedido sem Content-Length
ROTA_DE_ANEXO = "/api/notas/anexo"


def corpo_grande_demais(tamanho: str | None, limite: int = CORPO_MAXIMO) -> bool:
    """Recusado antes de ser lido: a checagem da rota só vem depois que o
    corpo inteiro já está na memória."""
    try:
        return int(tamanho or 0) > limite
    except ValueError:
        return True


# a rota que salva desenho: o texto vai dentro de um JSON, e cada aspa do
# desenho ganha uma barra; o dobro do maior desenho cobre o pior caso
ROTA_DE_DESENHO = "/api/desenhos/arquivo"
# a prévia em PNG do desenho, que a página exporta depois de salvar
ROTA_DE_PREVIA = "/api/desenhos/previa"
# a tela Arquivos: o corpo são os arquivos a converter ou montar
ROTAS_DE_ARQUIVOS = "/api/arquivos/"


def limite_do_corpo(metodo: str, caminho: str) -> int:
    from aide import arquivos
    from aide.storage import anexos, desenhos, previas

    if metodo == "POST" and caminho == ROTA_DE_ANEXO:
        return anexos.TAMANHO_MAXIMO
    if metodo == "PUT" and caminho == ROTA_DE_DESENHO:
        return 2 * desenhos.TAMANHO_MAXIMO
    if metodo == "PUT" and caminho == ROTA_DE_PREVIA:
        return previas.TAMANHO_MAXIMO
    if metodo == "POST" and caminho.startswith(ROTAS_DE_ARQUIVOS):
        return arquivos.TAMANHO_MAXIMO + arquivos.PLANO_MAXIMO
    return CORPO_MAXIMO


# ---------- quem está do outro lado da conexão ----------
#
# Escutar em 127.0.0.1 deixa de fora as outras máquinas, mas não as outras
# contas desta: um serviço do sistema rodando como outro usuário leria tudo
# com um curl, privado incluído, passando por cima da permissão da sua pasta
# pessoal. O Linux diz, em /proc/net/tcp, de que conta é cada socket: a ponta
# do cliente de cada conexão com esta porta tem o uid de quem a abriu.

TABELA_TCP = "/proc/net/tcp"


def _hex_ipv4(ip: str, porta: int) -> str:
    """'127.0.0.1', 8787 -> '0100007F:2253', como o /proc/net/tcp escreve."""
    import ipaddress
    import struct

    numero = struct.unpack("<I", ipaddress.IPv4Address(ip).packed)[0]
    return f"{numero:08X}:{porta:04X}"


def conta_da_conexao(cliente: tuple[str, int], servidor: tuple[str, int],
                     tabela: str = TABELA_TCP) -> int | None:
    """O uid de quem abriu a conexão, ou None se não deu para saber."""
    try:
        origem, destino = _hex_ipv4(*cliente), _hex_ipv4(*servidor)
        with open(tabela) as f:
            next(f, None)
            for linha in f:
                campos = linha.split()
                if len(campos) > 7 and campos[1] == origem and campos[2] == destino:
                    return int(campos[7])
    except (OSError, ValueError):
        return None
    return None


def conexao_permitida(scope) -> str | None:
    """None se a conexão é da conta dona do servidor; senão, o motivo.

    Na dúvida, recusa: sem saber de quem é, não entrega o privado. O cliente
    que não é endereço IP é o TestClient, que não abre conexão nenhuma — o
    endereço vem do transporte, nunca de cabeçalho (proxy_headers desligado
    no servidor; ver servidor.py)."""
    import ipaddress
    import os

    cliente, servidor = scope.get("client"), scope.get("server")
    if not cliente or not servidor:
        return "conexão sem origem conhecida"
    try:
        ipaddress.ip_address(cliente[0])
    except ValueError:
        return None
    dono = conta_da_conexao(tuple(cliente), tuple(servidor))
    if dono is None:
        return "não deu para saber de que conta vem a conexão"
    if dono != os.getuid():
        return "conexão de outra conta desta máquina"
    return None


def instalar(app) -> None:
    from fastapi.responses import PlainTextResponse

    @app.middleware("http")
    async def fronteira(request, call_next):
        host = request.headers.get("host", "")
        outra_conta = conexao_permitida(request.scope)
        if outra_conta:
            resposta = PlainTextResponse(outra_conta, status_code=403)
        elif not host_permitido(host):
            resposta = PlainTextResponse("host não permitido", status_code=421)
        else:
            motivo = escrita_permitida(
                request.method, host, request.headers.get("origin"),
                request.headers.get(CABECALHO_ESCRITA),
                request.headers.get("sec-fetch-site"))
            if motivo:
                resposta = PlainTextResponse(motivo, status_code=403)
            elif corpo_grande_demais(request.headers.get("content-length"),
                                     limite_do_corpo(request.method, request.url.path)):
                resposta = PlainTextResponse("pedido grande demais", status_code=413)
            else:
                resposta = await call_next(request)
        for nome, valor in CABECALHOS.items():
            resposta.headers.setdefault(nome, valor)
        # a página mostra privado; cópia em cache de disco é cópia fora do banco
        if "cache-control" not in resposta.headers:
            resposta.headers["cache-control"] = "no-store"
        return resposta
