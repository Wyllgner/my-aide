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
import os
import tempfile
import threading
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


def _json(texto: str, limite: int, nome: str) -> object:
    """O JSON de `texto`, conferido como o navegador vai ler, ou DesenhoInvalido."""
    if not isinstance(texto, str):
        raise DesenhoInvalido(f"{nome} tem de ser texto")
    try:
        tamanho = len(texto.encode("utf-8"))
    except UnicodeEncodeError:
        # um surrogate solto ("\ud800") passa pelo JSON do pedido mas não vira
        # UTF-8; sem isto, viraria erro 500 em vez de "desenho inválido"
        raise DesenhoInvalido("texto com caractere inválido") from None
    if tamanho > limite:
        raise DesenhoInvalido(f"{nome} grande demais")
    try:
        # NaN e Infinity o Python aceita e o JSON.parse do navegador não: o
        # arquivo seria gravado e depois não abriria no Excalidraw
        return json.loads(texto, parse_constant=_recusar)
    except (ValueError, RecursionError):
        raise DesenhoInvalido("não é JSON") from None


def _elementos_validos(elementos) -> bool:
    return isinstance(elementos, list) and all(
        isinstance(e, dict) and isinstance(e.get("type"), str) for e in elementos)


def validar(texto: str) -> dict:
    """O desenho lido de `texto`, ou DesenhoInvalido dizendo o porquê."""
    dados = _json(texto, TAMANHO_MAXIMO, "desenho")
    if not isinstance(dados, dict) or dados.get("type") != "excalidraw":
        raise DesenhoInvalido("não é um desenho do Excalidraw")
    if not _elementos_validos(dados.get("elements", [])):
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


# ---------- o privado que não se perde ----------

# A marcação mora no arquivo, e o excalidraw.com e o Obsidian descartam a
# chave "aide" ao salvar: editado lá, o desenho voltaria a ser público, e o
# assessor passaria a lê-lo. Por isso o servidor também guarda, em `data/`,
# quais desenhos são privados. Vale o que disser privado — o arquivo ou o
# registro —, e o registro só perde um desenho quando você desmarca a caixa
# aqui. Como nas notas: o privado só sobe por fora, descer é decisão sua.
#
# A chave é o caminho no vault: mover por aqui leva a marca junto; renomear
# por fora não leva (aí vale só a marcação do arquivo).
MARCAS = "desenhos-privados.json"
_TRAVA_MARCAS = threading.Lock()


def _arquivo_de_marcas(data_dir: Path) -> Path:
    return Path(data_dir) / MARCAS


def marcados(data_dir: Path) -> frozenset[str]:
    """Os caminhos marcados. Registro ilegível levanta OSError ou ValueError:
    quem pergunta por um desenho trata isso como privado."""
    try:
        lista = json.loads(_arquivo_de_marcas(data_dir).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return frozenset()
    if not isinstance(lista, list):
        raise ValueError("registro de desenhos privados inválido")  # noqa: TRY004 - conteúdo do arquivo, não argumento
    return frozenset(c for c in lista if isinstance(c, str))


def _gravar_marcas(data_dir: Path, caminhos: set[str]) -> None:
    destino = _arquivo_de_marcas(data_dir)
    destino.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporario = tempfile.mkstemp(dir=destino.parent, prefix=".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as saida:
            json.dump(sorted(caminhos), saida, ensure_ascii=False, indent=1)
        os.chmod(temporario, 0o600)
        os.replace(temporario, destino)
    except BaseException:
        Path(temporario).unlink(missing_ok=True)
        raise


def marcar(data_dir: Path, caminho: str, privada: bool) -> None:
    with _TRAVA_MARCAS:
        atuais = set(marcados(data_dir))
        if (caminho in atuais) == privada:
            return
        if privada:
            atuais.add(caminho)
        else:
            atuais.discard(caminho)
        _gravar_marcas(data_dir, atuais)


def mover_marcas(data_dir: Path, de: str, para: str) -> None:
    """O desenho `de` virou `para`; ou, com `de` sendo uma pasta, tudo que
    estava dentro dela foi junto."""
    with _TRAVA_MARCAS:
        atuais = set(marcados(data_dir))
        novos = set()
        for caminho in atuais:
            if caminho == de:
                novos.add(para)
            elif caminho.startswith(de + "/"):
                novos.add(para + caminho[len(de):])
            else:
                novos.add(caminho)
        if novos != atuais:
            _gravar_marcas(data_dir, novos)


def privado_de_fato(data_dir: Path, caminho: str, dados: dict | None) -> bool:
    """Privado pelo arquivo ou pelo registro. Achar a marcação no arquivo põe
    o registro em dia (desenho marcado antes do registro existir). `dados`
    None é desenho que não deu para ler: sem ler, conta como privado. Registro
    ilegível também: na dúvida, não sai."""
    try:
        if dados is not None and privado(dados):
            marcar(data_dir, caminho, True)
            return True
        return dados is None or caminho in marcados(data_dir)
    except (OSError, ValueError):
        return True


def texto_de(dados: dict) -> str:
    """O que está escrito no desenho, um trecho por linha: as caixas de texto
    (inclusive o rótulo dentro de uma forma, que é um texto preso a ela) e o
    nome dos frames. Elemento apagado fica no arquivo até o Excalidraw limpar;
    não conta."""
    trechos = []
    for elemento in dados.get("elements", []):
        if elemento.get("isDeleted") is True:
            continue
        if elemento.get("type") == "text":
            # o originalText é o que você digitou; o text vem quebrado na
            # largura da caixa
            escrito = elemento.get("originalText") or elemento.get("text")
        elif elemento.get("type") in ("frame", "magicframe"):
            escrito = elemento.get("name")
        else:
            continue
        if isinstance(escrito, str) and escrito.strip():
            trechos.append(escrito.strip())
    return "\n".join(trechos)


def links_de(dados: dict) -> list[str]:
    """Os links dos elementos (o campo "link", Ctrl+K no Excalidraw), cada um
    uma vez, na ordem do desenho. Elemento apagado não conta."""
    achados: dict[str, None] = {}
    for elemento in dados.get("elements", []):
        if not isinstance(elemento, dict) or elemento.get("isDeleted") is True:
            continue
        link = elemento.get("link")
        if isinstance(link, str) and link.strip():
            achados[link.strip()] = None
    return list(achados)


def gravar(caminho: Path, texto: str, privada: bool | None = None) -> dict:
    """Confere e grava por cima, de uma vez (`vault.gravar`). Devolve o desenho.

    O Excalidraw descarta a chave "aide" ao serializar a cena, então o texto
    que o editor manda chega sem ela. Sem pedido explícito (`privada=None`),
    vale a marcação do arquivo que já está no disco: salvar um desenho nunca
    o torna público por esquecimento. Só quando a marcação muda o texto é
    reescrito, com a mesma formatação do excalidraw.com.
    """
    dados = validar(texto)
    if privada is None:
        privada = caminho.is_file() and privado(ler(caminho)[1])
    if privado(dados) != privada:
        dados["aide"] = {**dados.get("aide", {}), "privada": privada}
        texto = json.dumps(dados, ensure_ascii=False, indent=2) + "\n"
    vault.gravar(caminho, texto)
    return dados


def criar(caminho: Path, texto: str | None = None) -> dict:
    """Cria sem sobrescrever (FileExistsError se já existe); vazio por padrão."""
    texto = vazio() if texto is None else texto
    dados = validar(texto)
    vault.criar_nota(caminho, texto)
    return dados


# ---------- achar o desenho que um link pede ----------


def indice(vault_dir: Path, arvore: list[dict] | None = None):
    """Os desenhos do vault para [[Casa.excalidraw]]: pelo nome em qualquer
    pasta (a da nota primeiro) ou pelo caminho, como os anexos e o Obsidian.
    Da árvore da página, que já deixa de fora oculto e link simbólico."""
    from aide.storage.anexos import Anexos
    from aide.storage.links import chave

    por_nome: dict[str, list[str]] = {}
    por_caminho: dict[str, str] = {}

    def visitar(itens: list[dict]) -> None:
        for item in itens:
            if item["tipo"] == "pasta":
                visitar(item["filhos"])
            elif item["tipo"] == "desenho":
                caminho = item["caminho"]
                # o Anexos procura com ".md" no fim (chave() o tira de volta)
                por_caminho[chave(caminho + ".md")] = caminho
                por_nome.setdefault(chave(caminho.rpartition("/")[2] + ".md"), []).append(caminho)

    visitar(vault.arvore(vault_dir) if arvore is None else arvore)
    return Anexos({k: tuple(v) for k, v in por_nome.items()}, por_caminho)


# ---------- a biblioteca de formas ----------

# Uma só, na raiz do vault, no formato do excalidraw.com (.excalidrawlib): o
# que você guarda para reusar vale em todo desenho e abre fora daqui também.
# O nome é fixo, nunca vem da página.
BIBLIOTECA = "Biblioteca.excalidrawlib"
# formas são vetor; uma biblioteca grande do site do Excalidraw tem centenas
# de KB. O limite cabe no corpo de pedido comum da fronteira (3 MB), mesmo com
# as aspas escapadas
TAMANHO_BIBLIOTECA = 1024 * 1024


def caminho_biblioteca(vault_dir: Path) -> Path:
    """Pela mesma porta dos outros arquivos: recusa se virou link simbólico."""
    return vault.resolver(vault_dir, BIBLIOTECA, extensoes=(".excalidrawlib",))


def biblioteca_vazia() -> str:
    return json.dumps({"type": "excalidrawlib", "version": 2, "source": "my-aide",
                       "libraryItems": []}, ensure_ascii=False, indent=2) + "\n"


def validar_biblioteca(texto: str) -> dict:
    dados = _json(texto, TAMANHO_BIBLIOTECA, "biblioteca")
    if not isinstance(dados, dict) or dados.get("type") != "excalidrawlib":
        raise DesenhoInvalido("não é uma biblioteca do Excalidraw")
    itens = dados.get("libraryItems")
    if not isinstance(itens, list) or not all(
            isinstance(i, dict) and _elementos_validos(i.get("elements")) for i in itens):
        raise DesenhoInvalido("itens da biblioteca inválidos")
    return dados


def ler_biblioteca(vault_dir: Path) -> tuple[str, dict]:
    """(texto, biblioteca); a vazia se o arquivo ainda não existe."""
    caminho = caminho_biblioteca(vault_dir)
    if not caminho.is_file():
        texto = biblioteca_vazia()
        return texto, validar_biblioteca(texto)
    if caminho.stat().st_size > TAMANHO_BIBLIOTECA:
        raise DesenhoInvalido("biblioteca grande demais")
    try:
        texto = caminho.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise DesenhoInvalido("não é texto UTF-8") from None
    return texto, validar_biblioteca(texto)


def gravar_biblioteca(vault_dir: Path, texto: str) -> dict:
    dados = validar_biblioteca(texto)
    vault.gravar(caminho_biblioteca(vault_dir), texto)
    return dados
