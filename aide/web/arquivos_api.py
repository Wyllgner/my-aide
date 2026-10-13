"""As rotas da tela Arquivos: recebem arquivos, devolvem o resultado.

Nada fica guardado. Os arquivos vão para uma pasta temporária enquanto chegam,
o resultado sai como resposta, e a pasta é apagada depois que a resposta foi
inteira — ou na hora, se o pedido falhar. O vault não é tocado.

Sem auditoria: a trilha registra o que mudou nos seus dados, e aqui nada muda.
A fronteira de escrita (Host, Origin, X-Aide) vale como em toda rota que não é
GET, e o limite de corpo é o desta tela (`seguranca.limite_do_corpo`).

O corpo é cru, como o do anexo: uma linha com o plano em JSON e, logo depois,
os arquivos colados na ordem do plano. Cada um tem o tamanho dito no plano.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from aide.arquivos import MAXIMO_DE_ARQUIVOS, PLANO_MAXIMO, TAMANHO_MAXIMO, pdf

ROTA_DE_MONTAR = "/api/arquivos/montar"


class PedidoInvalido(ValueError):
    pass


def ler_plano(texto: bytes) -> dict:
    """{"arquivos": [bytes de cada um], "paginas": [[arquivo, página], ...]}"""
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
    paginas = plano.get("paginas")
    if (not isinstance(paginas, list)
            or not all(isinstance(p, list) and len(p) == 2
                       and all(type(n) is int for n in p) for p in paginas)):
        raise PedidoInvalido("lista de páginas ilegível")
    return {"arquivos": tamanhos, "paginas": [tuple(p) for p in paginas]}


def instalar(app) -> None:
    from fastapi import HTTPException, Request
    from fastapi.responses import FileResponse
    from starlette.background import BackgroundTask
    from starlette.concurrency import run_in_threadpool

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

    async def montar(request):
        """O PDF com as páginas pedidas, na ordem pedida."""
        pasta = Path(tempfile.mkdtemp(prefix="aide-arquivos-"))
        try:
            plano, caminhos = await receber(request, pasta)
            destino = pasta / "resultado.pdf"
            await run_in_threadpool(pdf.montar, caminhos, plano["paginas"], destino)
        except (PedidoInvalido, pdf.PdfInvalido) as erro:
            shutil.rmtree(pasta, ignore_errors=True)
            raise HTTPException(400 if isinstance(erro, PedidoInvalido) else 422,
                                str(erro)) from None
        except BaseException:
            shutil.rmtree(pasta, ignore_errors=True)
            raise
        return FileResponse(destino, media_type="application/pdf",
                            headers={"cache-control": "no-store"},
                            background=BackgroundTask(shutil.rmtree, pasta, ignore_errors=True))

    # `from __future__ import annotations` deixa a anotação como texto, e o
    # FastAPI a procuraria nos globais, onde Request não está: vai o objeto,
    # antes de registrar a rota
    montar.__annotations__["request"] = Request
    app.post(ROTA_DE_MONTAR)(montar)
