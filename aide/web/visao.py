"""A visão geral do vault: o que o painel de notas mostra.

Tudo sai do mapa de links e das leituras em cache (`grafo.py`) — nenhuma
nota é relida para montar o painel se ela não mudou.

"Atividade" junta duas fontes: o registro de edições (`note_activity`), que
guarda cada dia em que a nota foi mexida, e a data de modificação do arquivo,
que cobre o que veio antes do registro existir.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from aide.storage import links
from aide.web import grafo


@dataclass
class Visao:
    notas: int = 0
    palavras: int = 0
    ligacoes: int = 0
    quebrados: int = 0
    orfas: list[str] = field(default_factory=list)  # sem link para nem de ninguém
    mais_citadas: list[tuple[str, int]] = field(default_factory=list)
    tags: list[tuple[str, int]] = field(default_factory=list)
    # (dia, notas mexidas) dos últimos `dias`, do mais antigo para hoje
    atividade: list[tuple[str, int]] = field(default_factory=list)


def montar(vault_dir: Path, agora: datetime, dias: int = 30,
           indice: links.Indice | None = None, conn=None) -> Visao:
    indice = indice or links.indice(vault_dir)
    lidas = grafo.leituras(vault_dir, indice)
    mapa = grafo.mapa(vault_dir, indice)

    # ligação é entre notas diferentes: link para si mesma não conecta nada
    entre_notas = [lig for lig in mapa.ligacoes
                   if lig.destino is not None and lig.destino != lig.origem]
    conectadas = {lig.origem for lig in entre_notas} | {lig.destino for lig in entre_notas}
    # cada nota que cita conta uma vez, mesmo citando três vezes
    citada_por = Counter(dest for dest, _ in {(lig.destino, lig.origem) for lig in entre_notas})

    tags: Counter = Counter()
    grafia: dict[str, str] = {}
    for leitura in lidas.values():
        for tag in leitura.tags:
            grafia.setdefault(tag.casefold(), tag)
            tags[tag.casefold()] += 1

    hoje = agora.date()
    inicio = hoje - timedelta(days=dias - 1)
    # (nota, dia): a mesma nota no mesmo dia conta uma vez, venha de onde vier
    mexidas = {(caminho, datetime.fromtimestamp(leitura.modificada, tz=agora.tzinfo).date())
               for caminho, leitura in lidas.items()}
    if conn is not None:
        from aide.storage import atividade

        mexidas |= {(caminho, date.fromisoformat(dia))
                    for caminho, dia in atividade.por_dia(conn, inicio)}
    por_dia: Counter = Counter(dia for _, dia in mexidas if inicio <= dia <= hoje)

    return Visao(
        notas=len(lidas),
        palavras=sum(leitura.palavras for leitura in lidas.values()),
        ligacoes=len({(lig.origem, lig.destino) for lig in entre_notas}),
        quebrados=len(mapa.quebrados()),
        orfas=sorted((c for c in lidas if c not in conectadas), key=str.casefold),
        mais_citadas=sorted(citada_por.items(), key=lambda par: (-par[1], par[0].casefold()))[:10],
        tags=[(grafia[t], n) for t, n in
              sorted(tags.items(), key=lambda par: (-par[1], par[0]))],
        atividade=[((hoje - timedelta(days=d)).isoformat(),
                    por_dia[hoje - timedelta(days=d)]) for d in range(dias - 1, -1, -1)],
    )
