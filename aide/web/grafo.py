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
from aide.web.markdown import Citacao, citacoes
from aide.web.notas_api import TAMANHO_MAXIMO

# caminho absoluto -> (mtime_ns, tamanho, citações). O tamanho entra porque
# duas gravações no mesmo instante podem ter o mesmo mtime em alguns discos
_CACHE: dict[Path, tuple[int, int, list[Citacao]]] = {}
_TRAVA = threading.Lock()


@dataclass(frozen=True)
class Ligacao:
    origem: str
    destino: str | None  # None: link quebrado
    citacao: Citacao


@dataclass
class Mapa:
    ligacoes: list[Ligacao] = field(default_factory=list)

    def entradas(self, caminho: str) -> list[Ligacao]:
        """Quem aponta para `caminho`, sem contar a própria nota."""
        return [lig for lig in self.ligacoes
                if lig.destino == caminho and lig.origem != caminho]

    def saidas(self, caminho: str) -> list[Ligacao]:
        return [lig for lig in self.ligacoes if lig.origem == caminho]

    def quebrados(self) -> list[Ligacao]:
        return [lig for lig in self.ligacoes if lig.destino is None]


def _citacoes_de(arquivo: Path) -> list[Citacao]:
    estado = arquivo.stat()
    if estado.st_size > TAMANHO_MAXIMO:
        # um export ou log de centenas de MB no vault não pode travar a tela
        return []
    marca = (estado.st_mtime_ns, estado.st_size)
    with _TRAVA:
        guardado = _CACHE.get(arquivo)
    if guardado and guardado[:2] == marca:
        return guardado[2]
    achadas = citacoes(arquivo.read_text(encoding="utf-8", errors="replace"))
    with _TRAVA:
        _CACHE[arquivo] = (*marca, achadas)
    return achadas


def mapa(vault_dir: Path, indice: links.Indice | None = None) -> Mapa:
    indice = indice or links.indice(vault_dir)
    resultado = Mapa()
    vistos = set()
    for origem in indice.caminhos:
        try:
            arquivo = vault.resolver(vault_dir, origem)
            achadas = _citacoes_de(arquivo)
        except (vault.ForaDoVault, OSError):
            continue
        vistos.add(arquivo)
        for citacao in achadas:
            resultado.ligacoes.append(
                Ligacao(origem, citacao.destino(origem, indice), citacao))
    with _TRAVA:
        # arquivo apagado ou renomeado não fica ocupando memória
        for velho in [p for p in _CACHE if p.is_relative_to(vault_dir.resolve())
                      and p not in vistos]:
            del _CACHE[velho]
    return resultado
