"""As rotas da tela Arquivos: recebem arquivos, devolvem o resultado.

Nada fica guardado. Os arquivos vão para uma pasta temporária enquanto chegam,
o resultado sai como resposta, e a pasta é apagada quando a resposta termina —
inteira, com erro ou com a conexão caindo no meio. O que nem isso alcança (o
serviço morto no meio de uma conversão, a máquina desligada) a varredura
apaga: pastas `aide-arquivos-*` com mais de uma hora somem ao subir o serviço
e a cada operação. O /tmp desta máquina fica em disco, e são documentos seus.
O vault não é tocado.

Sem auditoria: a trilha registra o que mudou nos seus dados, e aqui nada muda.
A fronteira de escrita (Host, Origin, X-Aide) vale como em toda rota que não é
GET, e o limite de corpo é o desta tela (`seguranca.limite_do_corpo`).

O corpo é cru, como o do anexo: uma linha com o plano em JSON e, logo depois,
os arquivos colados na ordem do plano. Cada um tem o tamanho dito no plano.
"""

from __future__ import annotations

import functools
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

from aide.arquivos import MAXIMO_DE_ARQUIVOS, PLANO_MAXIMO, TAMANHO_MAXIMO, converter, pdf

ROTA_DE_MONTAR = "/api/arquivos/montar"
ROTA_DE_CONVERTER = "/api/arquivos/converter"
ROTA_DE_IMAGENS = "/api/arquivos/imagens"
ROTA_DE_WORD = "/api/arquivos/word"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PREFIXO = "aide-arquivos-"
# Quantas operações de cada tipo rodam ao mesmo tempo. Quem espera a vez
# espera no laço de eventos, não numa thread: o grupo de threads é o mesmo das
# outras telas, e conversões na fila (até 120 s cada) o esgotariam.
VAGAS = {"converter": 1, "montar": 2}
# acima disto na fila, a resposta é "tente de novo", antes de receber o envio
FILA_MAXIMA = 4

# uma conversão grava na pasta ao menos a cada 120 s (o prazo de cada
# arquivo): uma hora sem mudar é pasta esquecida, não trabalho em andamento
ESQUECIDA = 3600


def varrer(base: Path | None = None, idade: float = ESQUECIDA) -> int:
    """Apaga as pastas temporárias desta tela que ficaram para trás. Só as
    nossas: o prefixo, dono igual a nós, pasta de verdade (link não)."""
    base = Path(base or tempfile.gettempdir())
    limite = time.time() - idade
    apagadas = 0
    try:
        candidatas = list(base.iterdir())
    except OSError:
        return 0
    for pasta in candidatas:
        try:
            info = pasta.lstat()
        except OSError:
            continue
        if (pasta.name.startswith(PREFIXO) and not pasta.is_symlink() and pasta.is_dir()
                and info.st_uid == os.getuid() and info.st_mtime < limite):
            shutil.rmtree(pasta, ignore_errors=True)
            apagadas += 1
    return apagadas


class PedidoInvalido(ValueError):
    pass


def ler_plano(texto: bytes) -> dict:
    """{"arquivos": [bytes de cada um], ...}: o resto é de cada rota."""
    try:
        plano = json.loads(texto)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise PedidoInvalido("plano ilegível") from None
    if not isinstance(plano, dict):
        raise PedidoInvalido("plano ilegível")
    tamanhos = plano.get("arquivos")
    if (not isinstance(tamanhos, list) or not 1 <= len(tamanhos) <= MAXIMO_DE_ARQUIVOS
            or not all(type(t) is int and t > 0 for t in tamanhos)):
        raise PedidoInvalido(f"mande de 1 a {MAXIMO_DE_ARQUIVOS} arquivos, nenhum vazio")
    return plano


def paginas_do(plano: dict) -> list[tuple[int, int]]:
    """"paginas": [[arquivo, página], ...], para montar."""
    paginas = plano.get("paginas")
    if (not isinstance(paginas, list)
            or not all(isinstance(p, list) and len(p) == 2
                       and all(type(n) is int for n in p) for p in paginas)):
        raise PedidoInvalido("lista de páginas ilegível")
    return [tuple(p) for p in paginas]


def nomes_do(plano: dict) -> list[str]:
    """"nomes": o nome de cada arquivo, que diz o formato ao LibreOffice e
    batiza o resultado. Só o nome: barra nenhuma vira caminho."""
    nomes = plano.get("nomes")
    if (not isinstance(nomes, list) or len(nomes) != len(plano["arquivos"])
            or not all(isinstance(n, str) and 0 < len(n) <= 255 for n in nomes)):
        raise PedidoInvalido("um nome para cada arquivo")
    return [n.replace("/", "_").replace("\\", "_") for n in nomes]


def sem_repetir(nomes: list[str]) -> list[str]:
    """'a.pdf', 'a.pdf' → 'a.pdf', 'a (2).pdf': o zip não guarda dois iguais."""
    vistos: dict[str, int] = {}
    saida = []
    for nome in nomes:
        base, ponto, ext = nome.rpartition(".")
        n = vistos[nome.lower()] = vistos.get(nome.lower(), 0) + 1
        saida.append(nome if n == 1 else f"{base} ({n}){ponto}{ext}")
    return saida


def imagens_de_todos(caminhos: list[Path], nomes: list[str], pasta: Path) -> tuple[Path, str]:
    """Cada página de cada PDF como PNG. Uma imagem só volta como .png; mais
    de uma, num .zip com "<pdf>-p01.png", "<pdf>-p02.png"…"""
    import zipfile

    por_pdf = [converter.para_imagens(c, n, pasta / f"imagens-{i}")
               for i, (c, n) in enumerate(zip(caminhos, nomes, strict=True))]
    total = sum(len(imagens) for imagens in por_pdf)
    if total > converter.MAXIMO_DE_IMAGENS:
        raise converter.ConversaoFalhou(f"mais de {converter.MAXIMO_DE_IMAGENS} páginas no total")
    if total == 1:
        return por_pdf[0][0], "image/png"
    bases = sem_repetir([n.rsplit(".", 1)[0] for n in nomes])
    pacote = pasta / "imagens.zip"
    # PNG já vem comprimido: guardar sem recomprimir é mais rápido e do mesmo tamanho
    with zipfile.ZipFile(pacote, "w", zipfile.ZIP_STORED) as z:
        for base, imagens in zip(bases, por_pdf, strict=True):
            casas = max(2, len(str(len(imagens))))
            for numero, imagem in enumerate(imagens, 1):
                z.write(imagem, f"{base}-p{numero:0{casas}d}.png")
    return pacote, "application/zip"


def _um_ou_zip(resultados: list[Path], nomes: list[str], ext: str, tipo: str,
               pasta: Path) -> tuple[Path, str]:
    """Um resultado volta como é; vários, num .zip com o nome de cada origem."""
    import zipfile

    if len(resultados) == 1:
        return resultados[0], tipo
    pacote = pasta / "convertidos.zip"
    finais = sem_repetir([n.rsplit(".", 1)[0] + "." + ext for n in nomes])
    with zipfile.ZipFile(pacote, "w", zipfile.ZIP_DEFLATED) as z:
        for resultado, nome in zip(resultados, finais, strict=True):
            z.write(resultado, nome)
    return pacote, "application/zip"


def converter_todos(caminhos: list[Path], nomes: list[str], pasta: Path) -> tuple[Path, str]:
    """Um PDF, ou um .zip com um PDF para cada documento."""
    pdfs = [converter.para_pdf(c, n, pasta / "saida") for c, n in zip(caminhos, nomes, strict=True)]
    return _um_ou_zip(pdfs, nomes, "pdf", "application/pdf", pasta)


def word_de_todos(caminhos: list[Path], nomes: list[str], pasta: Path,
                  modo: str) -> tuple[Path, str]:
    """Um .docx, ou um .zip com um .docx para cada PDF."""
    docs = [converter.para_word(c, n, pasta / f"word-{i}", modo)
            for i, (c, n) in enumerate(zip(caminhos, nomes, strict=True))]
    return _um_ou_zip(docs, nomes, "docx", DOCX, pasta)


@functools.cache
def resposta_que_limpa():
    """A classe da resposta: o FastAPI só é importado quando a web sobe."""
    from fastapi.responses import FileResponse

    class RespostaQueLimpa(FileResponse):
        """O arquivo e, saia como sair, a pasta dele apagada. O BackgroundTask
        do FileResponse só roda se a resposta for até o fim: Range inválido
        (400/416) ou conexão caída pulavam a limpeza. E Range é ignorado:
        nenhuma destas rotas entrega pedaço de arquivo."""

        def __init__(self, caminho: Path, pasta: Path, **kwargs):
            super().__init__(caminho, **kwargs)
            self.pasta = pasta

        async def __call__(self, scope, receive, send):
            sem_range = [(k, v) for k, v in scope.get("headers", []) if k.lower() != b"range"]
            try:
                await super().__call__({**scope, "headers": sem_range}, receive, send)
            finally:
                shutil.rmtree(self.pasta, ignore_errors=True)

    return RespostaQueLimpa


def instalar(app) -> None:
    import anyio
    from fastapi import HTTPException, Request

    RespostaQueLimpa = resposta_que_limpa()

    # o que um desligamento deixou para trás some ao subir
    varrer()

    async def receber(request, pasta: Path) -> tuple[dict, list[Path]]:
        """Lê o plano e grava os arquivos em `pasta` enquanto os bytes chegam,
        contando: o limite vale mesmo sem Content-Length."""
        fluxo = request.stream()
        cabeca = b""
        async for pedaco in fluxo:
            cabeca += pedaco
            if b"\n" in cabeca or len(cabeca) > PLANO_MAXIMO:
                break
        linha, separador, resto = cabeca.partition(b"\n")
        if not separador or len(linha) > PLANO_MAXIMO:
            raise PedidoInvalido("o pedido não começa com o plano")
        plano = ler_plano(linha)
        tamanhos = plano["arquivos"]
        if sum(tamanhos) > TAMANHO_MAXIMO:
            raise HTTPException(413, "arquivos grandes demais")

        caminhos = [pasta / f"entrada-{i}" for i in range(len(tamanhos))]
        atual, falta = 0, tamanhos[0]
        saida = caminhos[0].open("wb")

        def escrever(dados: bytes) -> None:
            nonlocal atual, falta, saida
            while dados:
                if atual >= len(tamanhos):
                    raise PedidoInvalido("vieram mais bytes do que o plano diz")
                parte, dados = dados[:falta], dados[falta:]
                saida.write(parte)
                falta -= len(parte)
                if not falta:
                    saida.close()
                    atual += 1
                    if atual < len(tamanhos):
                        falta = tamanhos[atual]
                        saida = caminhos[atual].open("wb")

        try:
            escrever(resto)
            async for pedaco in fluxo:
                escrever(pedaco)
        finally:
            saida.close()
        if atual < len(tamanhos):
            raise PedidoInvalido("vieram menos bytes do que o plano diz")
        return plano, caminhos

    import asyncio
    import weakref

    # um conjunto de limitadores por laço de eventos: o limitador pertence ao
    # laço em que nasceu, e quem espera nele vindo de outro laço nunca acorda.
    # No servidor há um laço só; nos testes, um por TestClient
    limitadores: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()

    def vaga(tipo: str) -> anyio.CapacityLimiter:
        deste_laco = limitadores.setdefault(asyncio.get_running_loop(), {})
        if tipo not in deste_laco:
            deste_laco[tipo] = anyio.CapacityLimiter(VAGAS[tipo])
        return deste_laco[tipo]

    async def operar(request, fazer, tipo: str):
        """Recebe, roda `fazer(plano, caminhos, pasta)` numa thread quando
        chega a vez dela e devolve o arquivo que produziu. A pasta some no fim,
        dê certo ou não."""
        limitador = vaga(tipo)
        if limitador.statistics().tasks_waiting >= FILA_MAXIMA:
            raise HTTPException(503, "há operações demais na fila; tente de novo em instantes")
        varrer()
        pasta = Path(tempfile.mkdtemp(prefix=PREFIXO))
        try:
            plano, caminhos = await receber(request, pasta)
            resultado, tipo_resultado = await anyio.to_thread.run_sync(
                fazer, plano, caminhos, pasta, limiter=limitador)
        except PedidoInvalido as erro:
            shutil.rmtree(pasta, ignore_errors=True)
            raise HTTPException(400, str(erro)) from None
        except (pdf.PdfInvalido, converter.ConversaoFalhou) as erro:
            shutil.rmtree(pasta, ignore_errors=True)
            raise HTTPException(422, str(erro)) from None
        except BaseException:
            shutil.rmtree(pasta, ignore_errors=True)
            raise
        return RespostaQueLimpa(resultado, pasta, media_type=tipo_resultado,
                                headers={"cache-control": "no-store"})

    def fazer_montagem(plano, caminhos, pasta):
        destino = pasta / "resultado.pdf"
        # "imagens": "proprias" é o imagens → PDF: cada foto na orientação dela
        pdf.montar(caminhos, paginas_do(plano), destino,
                   imagem_na_vizinha=plano.get("imagens") != "proprias")
        return destino, "application/pdf"

    def fazer_conversao(plano, caminhos, pasta):
        return converter_todos(caminhos, nomes_do(plano), pasta)

    def fazer_imagens(plano, caminhos, pasta):
        return imagens_de_todos(caminhos, nomes_do(plano), pasta)

    def fazer_word(plano, caminhos, pasta):
        modo = plano.get("modo", "aparencia")
        if modo not in converter.MODOS_WORD:
            raise PedidoInvalido("modo é aparencia ou texto")
        return word_de_todos(caminhos, nomes_do(plano), pasta, modo)

    async def montar(request):
        """O PDF com as páginas pedidas, na ordem pedida."""
        return await operar(request, fazer_montagem, "montar")

    async def converter_rota(request):
        """Documentos em PDF: um vira um PDF, vários viram um .zip."""
        return await operar(request, fazer_conversao, "converter")

    async def imagens(request):
        """PDFs em PNG, uma imagem por página."""
        return await operar(request, fazer_imagens, "converter")

    async def word(request):
        """PDFs em .docx, mantendo a aparência ou só o texto."""
        return await operar(request, fazer_word, "converter")

    # `from __future__ import annotations` deixa a anotação como texto, e o
    # FastAPI a procuraria nos globais, onde Request não está: vai o objeto,
    # antes de registrar a rota
    for rota, funcao in ((ROTA_DE_MONTAR, montar), (ROTA_DE_CONVERTER, converter_rota),
                         (ROTA_DE_IMAGENS, imagens), (ROTA_DE_WORD, word)):
        funcao.__annotations__["request"] = Request
        app.post(rota)(funcao)
