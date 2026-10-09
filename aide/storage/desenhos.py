"""Os desenhos do vault: arquivos `.excalidraw`, JSON puro.

O mesmo formato do excalidraw.com, que o plugin do Obsidian também abre: o
arquivo continua legível fora do projeto. Mora nas mesmas pastas das notas e
passa pela mesma porta (`vault.resolver`), só que com a sua extensão.

O que vem da página é conferido antes de chegar ao disco: tamanho, JSON, a
cara de uma cena do Excalidraw e as imagens embutidas, que só podem ser
`data:` de imagem. O texto aceito é gravado como veio, sem reformatar, para
um desenho mexido no Obsidian não virar outro arquivo no git a cada salvar.

Privado é uma chave nossa na raiz, `"aide": {"privada": true}`. O Excalidraw
ignora chave que não conhece, então o arquivo continua abrindo em todo lugar.
"""

from __future__ import annotations

import json
from pathlib import Path

from aide.storage import vault

EXTENSAO = ".excalidraw"
# imagem colada entra no JSON em base64; um desenho com algumas fotos passa de
# poucos MB, e mais do que isso já não é rascunho
TAMANHO_MAXIMO = 20 * 1024 * 1024
# os tipos que o próprio Excalidraw aceita colar como imagem (IMAGE_MIME_TYPES)
TIPOS_DE_IMAGEM = frozenset({"image/svg+xml", "image/png", "image/jpeg", "image/gif",
                             "image/webp", "image/bmp", "image/x-icon", "image/avif",
                             "image/jfif"})


class DesenhoInvalido(ValueError):
    """Texto que não é um desenho do Excalidraw que aceitamos gravar."""


def resolver(vault_dir: Path, relativo: str) -> Path:
    """Como `vault.resolver`, com a mesma recusa de `..`, oculto e link
    simbólico, mas só para `.excalidraw`."""
    return vault.resolver(vault_dir, relativo, extensoes=(EXTENSAO,))


def vazio() -> str:
    """O desenho novo: o que o excalidraw.com grava para uma tela em branco."""
    return json.dumps({
        "type": "excalidraw", "version": 2, "source": "my-aide",
        "elements": [], "appState": {"gridSize": None, "viewBackgroundColor": "#ffffff"},
        "files": {},
    }, ensure_ascii=False, indent=2) + "\n"


def validar(texto: str) -> dict:
    """O desenho lido de `texto`, ou DesenhoInvalido dizendo o porquê."""
    if not isinstance(texto, str):
        raise DesenhoInvalido("o desenho tem de ser texto")
    try:
        tamanho = len(texto.encode("utf-8"))
    except UnicodeEncodeError:
        # um surrogate solto ("\ud800") passa pelo JSON do pedido mas não vira
        # UTF-8; sem isto, viraria erro 500 em vez de "desenho inválido"
        raise DesenhoInvalido("texto com caractere inválido") from None
    if tamanho > TAMANHO_MAXIMO:
        raise DesenhoInvalido("desenho grande demais")
    try:
        # NaN e Infinity o Python aceita e o JSON.parse do navegador não: o
        # arquivo seria gravado e depois não abriria no Excalidraw
        dados = json.loads(texto, parse_constant=_recusar)
    except (ValueError, RecursionError):
        raise DesenhoInvalido("não é JSON") from None
    if not isinstance(dados, dict) or dados.get("type") != "excalidraw":
        raise DesenhoInvalido("não é um desenho do Excalidraw")
    elementos = dados.get("elements", [])
    if not isinstance(elementos, list) or not all(
            isinstance(e, dict) and isinstance(e.get("type"), str) for e in elementos):
        raise DesenhoInvalido("elementos inválidos")
    for campo in ("appState", "files"):
        if not isinstance(dados.get(campo, {}), dict):
            raise DesenhoInvalido(f"{campo} inválido")
    for arquivo in dados.get("files", {}).values():
        if not isinstance(arquivo, dict):
            raise DesenhoInvalido("imagem embutida inválida")
        url, tipo = arquivo.get("dataURL"), arquivo.get("mimeType")
        # só imagem, e só embutida: nada de endereço de fora nem outro esquema
        if tipo not in TIPOS_DE_IMAGEM or not isinstance(url, str) \
                or not url.startswith(f"data:{tipo};"):
            raise DesenhoInvalido("imagem embutida de tipo não aceito")
    aide = dados.get("aide", {})
    if not isinstance(aide, dict) or not isinstance(aide.get("privada", False), bool):
        raise DesenhoInvalido("marcação de privado inválida")
    return dados


def _recusar(constante: str):
    raise ValueError(constante)


def ler(caminho: Path) -> tuple[str, dict]:
    """(texto, desenho) do arquivo. O tamanho é conferido antes de ler: um
    arquivo enorme posto no vault por fora não chega a ir para a memória."""
    if caminho.stat().st_size > TAMANHO_MAXIMO:
        raise DesenhoInvalido("desenho grande demais")
    try:
        texto = caminho.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise DesenhoInvalido("não é texto UTF-8") from None
    return texto, validar(texto)


def privado(dados: dict) -> bool:
    return dados.get("aide", {}).get("privada", False) is True


def gravar(caminho: Path, texto: str) -> dict:
    """Confere e grava por cima, de uma vez (`vault.gravar`). Devolve o desenho."""
    dados = validar(texto)
    vault.gravar(caminho, texto)
    return dados


def criar(caminho: Path, texto: str | None = None) -> dict:
    """Cria sem sobrescrever (FileExistsError se já existe); vazio por padrão."""
    texto = vazio() if texto is None else texto
    dados = validar(texto)
    vault.criar_nota(caminho, texto)
    return dados
