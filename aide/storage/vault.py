"""Vault: as notas em markdown.

O arquivo é a fonte da verdade — legível sem o projeto, versionável em git.
O SQLite é índice: se ele sumir, dá para reconstruir a partir dos arquivos.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from pathlib import Path

SEPARADOR = "---"
LIXEIRA = ".trash"


INBOX = "Inbox"
# o que o Windows, o macOS ou o Obsidian não aceitam num nome de arquivo, ou
# que o Obsidian lê como sintaxe de link: [[a#b]], [[a^b]], [[a|b]]
PROIBIDOS = re.compile(r'[\\/:*?"<>|#^\[\]\x00-\x1f]')
TAMANHO_NOME = 100


def nome_de_arquivo(titulo: str) -> str:
    """'Reunião: orçamento' -> 'Reunião orçamento'. O título vira o nome do
    arquivo, com acento e espaço, como no Obsidian: é isso que deixa um
    [[Reunião orçamento]] achar a nota."""
    limpo = re.sub(r"\s+", " ", PROIBIDOS.sub(" ", unicodedata.normalize("NFC", titulo)))
    # ponto na frente esconderia o arquivo; no fim, o Windows tira sozinho
    limpo = limpo.strip(" .")[:TAMANHO_NOME].strip(" .")
    return limpo or "Sem título"


def caminho_para(vault_dir: Path, titulo: str) -> Path:
    """`Inbox/Título.md`. As notas do assessor caem numa pasta só, e você as
    leva para onde quiser pela página; repetido vira `Título 2.md`."""
    pasta = vault_dir / INBOX
    base = nome_de_arquivo(titulo)
    caminho = pasta / f"{base}.md"
    contador = 2
    while caminho.exists():
        caminho = pasta / f"{base} {contador}.md"
        contador += 1
    return caminho


def para_lixeira(vault_dir: Path, caminho: Path) -> Path | None:
    """Tira o arquivo do vault sem destruí-lo, e devolve onde ele foi parar.

    Apagar uma nota tem de ser um ato completo: enquanto o arquivo ficava no
    vault com a linha marcada como apagada, ele não aparecia em lugar nenhum e
    nem a reindexação o alcançava, porque ela varre as linhas. Com o arquivo
    fora, vale uma regra só: o que está no vault é nota viva.

    Não é destruição. O texto continua legível em `vault/.trash/`, e voltar é um
    `mv`. O que deixa de existir é o meio-caminho.
    """
    if not caminho.exists():
        return None
    destino = vault_dir / LIXEIRA / caminho.name
    contador = 2
    while destino.exists():
        destino = vault_dir / LIXEIRA / f"{caminho.stem}-{contador}{caminho.suffix}"
        contador += 1
    destino.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    caminho.replace(destino)
    return destino


def arquivos(vault_dir: Path) -> list[Path]:
    """Todo markdown do vault, menos a lixeira. Ordem estável, para o relato
    de uma reindexação sair igual duas vezes."""
    if not vault_dir.exists():
        return []
    return sorted(p for p in vault_dir.rglob("*.md")
                  if LIXEIRA not in p.relative_to(vault_dir).parts)


def escrever(caminho: Path, titulo: str, corpo: str, tags: str | None,
             criada_em: datetime, privada: bool = False) -> None:
    # nota é texto puro com a sua vida dentro; nasce só sua
    caminho.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    frontmatter = [
        SEPARADOR,
        f"title: {titulo}",
        f"created: {criada_em.isoformat(timespec='minutes')}",
    ]
    if tags:
        frontmatter.append(f"tags: [{tags}]")
    if privada:
        # no arquivo, e não só no banco: o arquivo é a fonte da verdade, e uma
        # reindexação a partir dele não pode desfazer o privado
        frontmatter.append("private: true")
    frontmatter.append(SEPARADOR)
    caminho.write_text("\n".join(frontmatter) + "\n\n" + corpo.strip() + "\n")
    caminho.chmod(0o600)


def acrescentar(caminho: Path, texto: str, quando: datetime) -> None:
    with caminho.open("a") as arquivo:
        arquivo.write(f"\n\n_{quando.strftime('%d/%m/%Y %H:%M')}_\n\n{texto.strip()}\n")


def inicio_do_corpo(texto: str) -> int:
    """A linha onde o corpo começa: 0 sem frontmatter, senão a seguinte à
    linha `---` que o fecha. É o que liga uma linha da prévia à do arquivo."""
    linhas = texto.split("\n")
    if not linhas or linhas[0].rstrip("\r") != SEPARADOR:
        return 0
    for fim in range(1, len(linhas)):
        if linhas[fim].rstrip("\r") == SEPARADOR:
            return fim + 1
    return 0


def separar(texto: str) -> tuple[dict[str, str], str]:
    """(frontmatter, corpo) de um texto de nota. Sem frontmatter também serve.

    O frontmatter é o do Obsidian: a primeira linha é `---` sozinha e ele vai
    até a próxima linha `---` sozinha. Partir no primeiro "---" que aparecer
    cortava a nota ao meio quando um valor ou o próprio corpo tinha um.
    """
    inicio = inicio_do_corpo(texto)
    if not inicio:
        return {}, texto.strip()
    linhas = texto.split("\n")
    meta = {}
    for linha in linhas[1:inicio - 1]:
        if ":" in linha:
            chave, valor = linha.split(":", 1)
            meta[chave.strip()] = valor.strip()
    return meta, "\n".join(linhas[inicio:]).strip()


def ler(caminho: Path) -> tuple[dict[str, str], str]:
    """Devolve (frontmatter, corpo) do arquivo."""
    return separar(caminho.read_text())


def privada(meta: dict[str, str]) -> bool:
    """`private: true` no frontmatter. Qualquer outra coisa é nota normal."""
    return meta.get("private", "").strip().lower() in ("true", "yes", "sim", "1")


def corpo_de(caminho: Path) -> str:
    return ler(caminho)[1]


# ---------- caminhos vindos de fora ----------


class ForaDoVault(ValueError):
    """Caminho que não é de uma nota ou pasta do vault."""


def resolver(vault_dir: Path, relativo: str, pasta: bool = False) -> Path:
    """O caminho de `relativo` dentro do vault, ou ForaDoVault.

    É a única porta por onde um caminho escrito na página chega ao disco, e
    por isso recusa tudo que não for, sem dúvida, uma nota ou pasta comum:
    `..`, caminho absoluto, barra invertida, nome oculto (`.trash`, `.obsidian`,
    `.git`) e link simbólico em qualquer ponto do caminho — um link dentro do
    vault apontando para fora transformaria "salvar nota" em escrever em
    qualquer lugar da sua pasta pessoal.
    """
    if not isinstance(relativo, str) or not relativo.strip():
        raise ForaDoVault("caminho vazio")
    if "\\" in relativo or "\x00" in relativo or relativo.startswith("/"):
        raise ForaDoVault("caminho inválido")
    partes = relativo.split("/")
    for parte in partes:
        if parte in ("", ".", "..") or parte.startswith(".") or parte != parte.strip():
            raise ForaDoVault(f"trecho inválido no caminho: {parte!r}")
        if PROIBIDOS.search(parte) or len(parte.encode()) > 255:
            raise ForaDoVault(f"nome inválido: {parte!r}")
    if not pasta and not partes[-1].lower().endswith(".md"):
        raise ForaDoVault("só arquivos .md")

    base = vault_dir.resolve()
    caminho = base.joinpath(*partes)
    atual = base
    for parte in partes:
        atual = atual / parte
        if atual.is_symlink():
            raise ForaDoVault("link simbólico no caminho")
    if not caminho.resolve().is_relative_to(base):
        raise ForaDoVault("caminho fora do vault")
    return caminho


def relativo_de(vault_dir: Path, caminho: Path) -> str:
    """O inverso de `resolver`: o que a página mostra e manda de volta."""
    return caminho.resolve().relative_to(vault_dir.resolve()).as_posix()


def arvore(vault_dir: Path) -> list[dict]:
    """Pastas e notas, pastas primeiro, em ordem alfabética sem caixa.

    Cada item: {nome, caminho, tipo: "pasta" | "nota", filhos}. Fica de fora o
    que `resolver` recusaria — oculto, link simbólico, o que não é .md —, para
    a página nunca oferecer um clique que vai dar erro.
    """
    def ramo(pasta: Path, prefixo: str) -> list[dict]:
        itens = []
        for filho in pasta.iterdir():
            if filho.name.startswith(".") or filho.is_symlink():
                continue
            caminho = f"{prefixo}{filho.name}"
            if filho.is_dir():
                itens.append({"nome": filho.name, "caminho": caminho, "tipo": "pasta",
                              "filhos": ramo(filho, caminho + "/")})
            elif filho.suffix.lower() == ".md":
                itens.append({"nome": filho.stem, "caminho": caminho, "tipo": "nota",
                              "filhos": []})
        return sorted(itens, key=lambda i: (i["tipo"] != "pasta", i["nome"].casefold()))

    return ramo(vault_dir, "") if vault_dir.is_dir() else []


def gravar(caminho: Path, texto: str) -> None:
    """Grava a nota inteira de uma vez: num arquivo ao lado e depois por cima.

    Com salvamento automático a cada pausa na digitação, uma queda no meio de
    um `write_text` deixaria a nota pela metade. A troca por `os.replace` é
    atômica: ou fica a versão velha, ou a nova.
    """
    import os
    import tempfile

    caminho.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporario = tempfile.mkstemp(dir=caminho.parent, prefix=".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as arquivo:
            arquivo.write(texto)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.chmod(temporario, 0o600)
        os.replace(temporario, caminho)
    except BaseException:
        Path(temporario).unlink(missing_ok=True)
        raise


def criar_nota(caminho: Path, texto: str = "") -> None:
    """Cria sem sobrescrever: se já existe, FileExistsError."""
    caminho.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with caminho.open("x", encoding="utf-8") as arquivo:
        arquivo.write(texto)
    caminho.chmod(0o600)


def criar_pasta(caminho: Path) -> None:
    caminho.mkdir(parents=True, exist_ok=False, mode=0o700)


def mover(origem: Path, destino: Path) -> None:
    """Renomeia ou move um arquivo de nota sem nunca passar por cima de outro.

    `os.rename` sobrescreve o destino calado; criar o nome novo como link
    para o mesmo arquivo falha se ele já existe, e só então o velho sai. Os
    dois nomes nunca somem juntos: no pior caso sobra o arquivo com os dois.
    """
    import errno
    import os

    destino.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.link(origem, destino)
    except FileExistsError:
        raise
    except OSError as erro:
        # disco sem link físico (exFAT, algumas pastas sincronizadas): confere
        # e renomeia. Sobra uma janela mínima entre conferir e renomear, que
        # só um segundo programa escrevendo o mesmo nome no mesmo instante
        # alcançaria
        if erro.errno not in (errno.EPERM, errno.ENOTSUP, errno.EOPNOTSUPP, errno.EXDEV,
                              errno.EMLINK):
            raise
        if destino.exists():
            raise FileExistsError(destino) from None
        os.rename(origem, destino)
        return
    os.unlink(origem)


def mover_pasta(origem: Path, destino: Path) -> None:
    """Move uma pasta inteira. Destino que já existe é recusado antes: renomear
    pasta por cima de pasta vazia seria aceito pelo sistema calado."""
    if destino.exists():
        raise FileExistsError(destino)
    destino.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    origem.rename(destino)
