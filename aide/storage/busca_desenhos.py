"""Busca por palavra no texto dos desenhos.

Os desenhos não estão no banco: a busca lê os arquivos, guardando em memória
o texto de cada um junto com o mtime — mudou o arquivo, lê de novo. Um vault
tem dezenas de desenhos, não milhares, e o texto deles é curto.

Privacidade:
- desenho privado (`"aide": {"privada": true}` no arquivo, ou no registro de
  `desenhos.marcados`, que não se perde quando o Obsidian reescreve o
  arquivo) só aparece para quem pode ver privado — e o assessor nunca o vê, nem com `ver_privado`, como as notas no
  `notes.search`;
- desenho que não deu para ler (inválido, grande demais) conta como privado:
  sem ler, não dá para saber se ele é;
- nada aqui vira embedding: isso mandaria o texto para a OpenAI. A busca é só
  por palavra, na máquina;
- a biblioteca de formas (`.excalidrawlib`) não tem marca de privado e pode
  guardar forma copiada de desenho privado: fica de fora, por não ser
  `.excalidraw`.
"""

from __future__ import annotations

import re
import threading
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from aide.storage import desenhos, vault
from aide.storage.search import termos_da_consulta

# o trecho em volta da primeira palavra achada
_EM_VOLTA = 60


@dataclass(frozen=True)
class Leitura:
    privado: bool  # a marcação do arquivo; o registro se confere à parte
    texto: str
    legivel: bool = True


_ILEGIVEL = Leitura(privado=True, texto="", legivel=False)
# caminho absoluto -> (mtime_ns, tamanho, leitura)
_CACHE: dict[Path, tuple[int, int, Leitura]] = {}
_TRAVA = threading.Lock()


def ler(arquivo: Path) -> Leitura:
    estado = arquivo.stat()
    marca = (estado.st_mtime_ns, estado.st_size)
    with _TRAVA:
        guardada = _CACHE.get(arquivo)
    if guardada and guardada[:2] == marca:
        return guardada[2]
    try:
        _, dados = desenhos.ler(arquivo)
        leitura = Leitura(desenhos.privado(dados), desenhos.texto_de(dados))
    except (desenhos.DesenhoInvalido, OSError):
        leitura = _ILEGIVEL
    with _TRAVA:
        _CACHE[arquivo] = (*marca, leitura)
    return leitura


def privado(data_dir: Path, caminho: str, leitura: Leitura) -> bool:
    """Privado de fato: pelo arquivo, pelo registro, ou por não dar para ler."""
    if not leitura.legivel:
        return True
    return desenhos.privado_de_fato(data_dir, caminho,
                                    {"aide": {"privada": True}} if leitura.privado else {})


def _dobrar(texto: str) -> str:
    """Sem acento e sem caixa, letra por letra: o resultado tem o mesmo
    tamanho do original, e a posição achada nele vale no original. É o que o
    FTS5 das notas faz (unicode61 tira os acentos)."""
    return "".join((unicodedata.normalize("NFKD", c)[:1] or c).casefold()[:1] or c
                   for c in texto)


def _trecho(texto: str, inicio: int, fim: int) -> str:
    antes = texto[max(0, inicio - _EM_VOLTA):inicio]
    depois = texto[fim:fim + _EM_VOLTA]
    trecho = (("…" if inicio > _EM_VOLTA else "") + antes + texto[inicio:fim] + depois
              + ("…" if len(texto) - fim > _EM_VOLTA else ""))
    return " ".join(trecho.split())


def buscar(vault_dir: Path, consulta: str, incluir_privados: bool, *, data_dir: Path,
           limite: int = 20) -> list[dict]:
    """Os desenhos com alguma das palavras da consulta, no nome ou no texto.
    Palavra inteira, como no FTS5: "casa" não acha "casamento". Primeiro os
    que têm mais palavras diferentes da consulta."""
    termos = [_dobrar(t) for t in termos_da_consulta(consulta)]
    if not termos:
        return []
    padroes = [re.compile(r"(?<!\w)" + re.escape(t) + r"(?!\w)") for t in termos]
    achados = []
    vistos: set[Path] = set()
    for caminho in desenhos.indice(vault_dir).por_caminho.values():
        try:
            arquivo = desenhos.resolver(vault_dir, caminho)
            leitura = ler(arquivo)
        except (vault.ForaDoVault, OSError):
            continue
        vistos.add(arquivo)
        e_privado = privado(data_dir, caminho, leitura)
        if e_privado and not incluir_privados:
            continue
        titulo = caminho.rpartition("/")[2].removesuffix(desenhos.EXTENSAO)
        no_titulo, no_texto = _dobrar(titulo), _dobrar(leitura.texto)
        distintos, vezes, primeiro = 0, 0, None
        for padrao in padroes:
            casos = list(padrao.finditer(no_texto))
            if casos or padrao.search(no_titulo):
                distintos += 1
            vezes += len(casos)
            if casos and (primeiro is None or casos[0].start() < primeiro.start()):
                primeiro = casos[0]
        if not distintos:
            continue
        trecho = (_trecho(leitura.texto, primeiro.start(), primeiro.end()) if primeiro
                  else " ".join(leitura.texto[:_EM_VOLTA * 2].split()))
        achados.append({"caminho": caminho, "titulo": titulo, "trecho": trecho,
                        "privado": e_privado, "_ordem": (-distintos, -vezes,
                                                                caminho.casefold())})
    achados.sort(key=lambda a: a["_ordem"])
    for achado in achados:
        del achado["_ordem"]
    _esquecer(vault_dir, vistos)
    return achados[:limite]


def _esquecer(vault_dir: Path, vistos: set[Path]) -> None:
    """Desenho apagado ou renomeado não fica ocupando memória."""
    raiz = vault_dir.resolve()
    with _TRAVA:
        for velho in [p for p in _CACHE if p.is_relative_to(raiz) and p not in vistos]:
            del _CACHE[velho]
