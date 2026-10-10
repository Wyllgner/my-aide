"""O mapa de links do vault: quem aponta para quem.

Calculado dos arquivos, não guardado no banco. Uma tabela de links só ficaria
certa depois da reindexação de quinze minutos, e o que você escreve no
Obsidian sumiria dos backlinks até lá. Ler e analisar cada nota a cada tela
também não precisa: o que se guarda, em memória, são os links de cada arquivo
junto com a data de modificação dele — mudou o arquivo, lê de novo.

O destino de cada link é resolvido na hora, porque ele muda sem o arquivo
mudar: criar a nota "Fornecedores" conserta o [[Fornecedores]] de outra.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path

from aide.storage import links, vault
from aide.web.markdown import Citacao, citacoes_separadas, etiquetas
from aide.web.notas_api import TAMANHO_MAXIMO


@dataclass(frozen=True)
class Leitura:
    """O que se tira de uma nota de uma vez só, e se guarda até ela mudar."""

    citacoes: list[Citacao]
    tags: list[str]
    palavras: int
    modificada: float  # mtime, para a atividade por dia
    privada: bool = False  # `private: true` no frontmatter
    # os [[...excalidraw]]: fora de `citacoes`, que é o mapa entre notas
    desenhos: list[Citacao] = field(default_factory=list)


VAZIA = Leitura([], [], 0, 0.0)

# caminho absoluto -> (mtime_ns, tamanho, leitura). O tamanho entra porque
# duas gravações no mesmo instante podem ter o mesmo mtime em alguns discos
_CACHE: dict[Path, tuple[int, int, Leitura]] = {}
_TRAVA = threading.Lock()


@dataclass(frozen=True)
class Ligacao:
    origem: str
    destino: str | None  # None: link quebrado
    citacao: Citacao


@dataclass
class Mapa:
    ligacoes: list[Ligacao] = field(default_factory=list)
    # nota -> desenho, à parte: quem conta notas, ligações e órfãs (a visão
    # geral, o assessor, o renomear de nota) não vê desenho como nota
    desenhos: list[Ligacao] = field(default_factory=list)

    def entradas(self, caminho: str) -> list[Ligacao]:
        """Quem aponta para `caminho`, sem contar a própria nota."""
        return [lig for lig in self.ligacoes
                if lig.destino == caminho and lig.origem != caminho]

    def saidas(self, caminho: str) -> list[Ligacao]:
        return [lig for lig in self.ligacoes if lig.origem == caminho]

    def quebrados(self) -> list[Ligacao]:
        return [lig for lig in self.ligacoes if lig.destino is None]

    def citam_desenho(self, caminho: str) -> list[Ligacao]:
        """As notas que levam ao desenho `caminho`."""
        return [lig for lig in self.desenhos if lig.destino == caminho]

    def desenhos_quebrados(self) -> list[Ligacao]:
        return [lig for lig in self.desenhos if lig.destino is None]


def ler(arquivo: Path) -> Leitura:
    estado = arquivo.stat()
    if estado.st_size > TAMANHO_MAXIMO:
        # um export ou log de centenas de MB no vault não pode travar a tela
        # sem ler, não dá para saber se é privada: para quem pergunta de fora,
        # trate como se fosse
        return Leitura([], [], 0, estado.st_mtime, privada=True)
    marca = (estado.st_mtime_ns, estado.st_size)
    with _TRAVA:
        guardado = _CACHE.get(arquivo)
    if guardado and guardado[:2] == marca:
        return guardado[2]
    texto = arquivo.read_text(encoding="utf-8", errors="replace")
    meta, corpo = vault.separar(texto)
    notas, de_desenhos = citacoes_separadas(texto)
    leitura = Leitura(notas, etiquetas(texto), len(corpo.split()),
                      estado.st_mtime, vault.privada(meta), de_desenhos)
    with _TRAVA:
        _CACHE[arquivo] = (*marca, leitura)
    return leitura


def leituras(vault_dir: Path, indice: links.Indice) -> dict[str, Leitura]:
    """A leitura de cada nota do vault, pelo caminho; tira do cache quem sumiu."""
    resultado: dict[str, Leitura] = {}
    vistos = set()
    for caminho in indice.caminhos:
        try:
            arquivo = vault.resolver(vault_dir, caminho)
            resultado[caminho] = ler(arquivo)
        except (vault.ForaDoVault, OSError):
            continue
        vistos.add(arquivo)
    with _TRAVA:
        # arquivo apagado ou renomeado não fica ocupando memória
        for velho in [p for p in _CACHE if p.is_relative_to(vault_dir.resolve())
                      and p not in vistos]:
            del _CACHE[velho]
    return resultado


def mapa(vault_dir: Path, indice: links.Indice | None = None, desenhos=None) -> Mapa:
    """`desenhos`: o índice de `desenhos.indice`, se quem chama já o tem."""
    from aide.storage import desenhos as desenhos_

    indice = indice or links.indice(vault_dir)
    if desenhos is None:
        desenhos = desenhos_.indice(vault_dir)
    resultado = Mapa()
    for origem, leitura in leituras(vault_dir, indice).items():
        for citacao in leitura.citacoes:
            resultado.ligacoes.append(
                Ligacao(origem, citacao.destino(origem, indice), citacao))
        for citacao in leitura.desenhos:
            resultado.desenhos.append(
                Ligacao(origem, desenhos.resolver(citacao.alvo, origem), citacao))
    return resultado
