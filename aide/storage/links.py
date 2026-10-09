"""Para onde aponta um [[link]] entre notas.

A regra é a do Obsidian, para o mesmo vault funcionar igual aqui e lá: o
link é o nome do arquivo sem `.md`, sem diferença de maiúscula; com pasta na
frente (`[[Projetos/Casa]]`), vale o caminho. Dois arquivos com o mesmo nome
em pastas diferentes: ganha o da pasta da nota que tem o link, depois o de
caminho mais curto, depois o primeiro em ordem alfabética — sempre o mesmo,
para o link não mudar de destino entre uma abertura e outra.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from pathlib import Path

from aide.storage import vault


def chave(texto: str) -> str:
    """O que conta para comparar: sem caixa, sem `.md`, e com o acento numa
    forma só — "ã" pode chegar como um caractere ou como "a" mais o til."""
    texto = unicodedata.normalize("NFC", texto.strip()).casefold()
    return texto.removesuffix(".md")


@dataclass(frozen=True)
class Indice:
    """Os caminhos do vault, prontos para resolver link sem ler o disco."""

    por_nome: dict[str, tuple[str, ...]]
    por_caminho: dict[str, str]

    @property
    def caminhos(self) -> list[str]:
        return sorted(self.por_caminho.values(), key=str.casefold)

    def resolver(self, alvo: str, origem: str | None = None) -> str | None:
        """O caminho (`Pasta/Nota.md`) para onde `alvo` aponta, ou None."""
        procurada = chave(alvo).strip("/")
        if not procurada:
            return None
        if "/" in procurada:
            if procurada in self.por_caminho:
                return self.por_caminho[procurada]
            # `[[Casa/Telhado]]` vale para `Projetos/Casa/Telhado.md`
            sufixo = [c for k, c in self.por_caminho.items() if k.endswith("/" + procurada)]
            return _melhor(sufixo, origem)
        return _melhor(list(self.por_nome.get(procurada, ())), origem)


def _melhor(candidatos: list[str], origem: str | None) -> str | None:
    if not candidatos:
        return None
    pasta = origem.rpartition("/")[0] if origem else None
    return min(candidatos, key=lambda c: (c.rpartition("/")[0] != pasta,
                                          c.count("/"), c.casefold()))


def indice(vault_dir: Path, arvore: list[dict] | None = None) -> Indice:
    """A partir da árvore do vault (a mesma que a página mostra). Quem já a
    tem em mãos passa, para a pasta não ser varrida duas vezes."""
    por_nome: dict[str, list[str]] = {}
    por_caminho: dict[str, str] = {}

    def visitar(itens: list[dict]) -> None:
        for item in itens:
            if item["tipo"] == "pasta":
                visitar(item["filhos"])
                continue
            caminho = item["caminho"]
            por_caminho[chave(caminho)] = caminho
            por_nome.setdefault(chave(item["nome"]), []).append(caminho)

    visitar(vault.arvore(vault_dir) if arvore is None else arvore)
    return Indice({k: tuple(v) for k, v in por_nome.items()}, por_caminho)
