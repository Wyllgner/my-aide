"""Ícones desenhados, não emoji.

Traço em grade de 20px, mesma espessura em todos: assim escalam e recolorem
junto com o texto, em vez de virar um bloco de fonte que o sistema desenha do
jeito dele.
"""

from __future__ import annotations

TRACOS = {
    "painel": "M3.5 11h4v5.5h-4zM8.5 6h4v10.5h-4zM13.5 8.5h3v8h-3",
    "hoje": "M3 9.5 10 4l7 5.5V16a1 1 0 0 1-1 1h-3.5v-4.5h-5V17H4a1 1 0 0 1-1-1z",
    "calendario": "M4 5h12v12H4zM4 8.5h12M7.5 3.5v3M12.5 3.5v3",
    "conversas": "M4 4h12v9H8l-4 3.5z",
    "notas": "M5 3h7l3 3v11H5zM12 3v3.5h3",
    "gastos": "M10 3.5v13M6.5 6.5h5a2 2 0 0 1 0 4h-3a2 2 0 0 0 0 4h5",
    "custo": "M4 15V9M8 15V5M12 15v-7M16 15v-4",
    "memoria": "M6.5 4.5a3 3 0 0 1 7 0v1a3 3 0 0 1 0 6v1a3 3 0 0 1-7 0z",
    "pessoas": ("M10 9.5a2.75 2.75 0 1 0 0-5.5 2.75 2.75 0 0 0 0 5.5z"
                "M4.5 16.5c0-3 2.5-4.5 5.5-4.5s5.5 1.5 5.5 4.5"),
    "fila": "M4 5.5h12M4 10h12M4 14.5h7",
    "ferramentas": ("M12.5 3.5a3.5 3.5 0 0 0-4.6 4.4L3.5 12.3v3.2h3.2l4.4-4.4"
                    "a3.5 3.5 0 0 0 4.4-4.6l-2.2 2.2-2-2z"),
    "auditoria": "M8.5 12.5a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM11.5 11.5 16 16",
    # relógio: lembrete é hora marcada, e na lista ele fica ao lado de tarefa,
    # que tem prazo. O ícone é o que distingue as duas coisas de longe.
    "reminders": "M10 17a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM10 6.5V10l2.5 1.5",
    # as ações da nota
    "editar": "M4 16l.8-3.6 8.4-8.4 2.8 2.8-8.4 8.4zM11.5 5.7l2.8 2.8",
    "dividido": "M3.5 4.5h13v11h-13zM10 4.5v11",
    "ler": ("M3.5 5c2.5-1 4.5-1 6.5.5 2-1.5 4-1.5 6.5-.5v10.5c-2.5-1-4.5-1-6.5.5"
            "-2-1.5-4-1.5-6.5-.5zM10 5.5V16"),
    "privada": "M5.5 9h9v7.5h-9zM7.5 9V6.5a2.5 2.5 0 0 1 5 0V9",
    "renomear": "M3.5 6.5h13v7h-13zM7 8.5v3",
    "lixeira": "M4 6h12M8 6V4h4v2M5.5 6l.8 10.5h7.4L14.5 6M8.5 9v5M11.5 9v5",
    # a lateral das notas
    "nova-nota": "M5 3h7l3 3v11H5zM12 3v3.5h3M10 9v5M7.5 11.5h5",
    "nova-pasta": "M3 5.5h5l1.5 2H17v8.5H3zM10 9.5v4.5M7.75 11.75h4.5",
    "grafo": ("M8 6a2 2 0 1 1-4 0 2 2 0 0 1 4 0zM16.5 8.5a2 2 0 1 1-4 0 2 2 0 0 1 4 0z"
              "M10.5 15a2 2 0 1 1-4 0 2 2 0 0 1 4 0zM7.9 6.6l4.7 1.3M6.6 7.9l1.3 5.2"
              "M13.2 10.2l-3.6 3.2"),
    "quebrado": ("M8.5 11.5l-2 2a2.5 2.5 0 0 1-3.5-3.5l2-2M11.5 8.5l2-2a2.5 2.5 0 0 1"
                 " 3.5 3.5l-2 2M7 3.5v2M3.5 7h2M13 16.5v-2M16.5 13h-2"),
}


def icone(nome: str, tamanho: int = 20) -> str:
    traco = TRACOS.get(nome, "M4 10h12")
    return (f'<svg width="{tamanho}" height="{tamanho}" viewBox="0 0 20 20" fill="none" '
            f'stroke="currentColor" stroke-width="1.5" stroke-linecap="round" '
            f'stroke-linejoin="round" aria-hidden="true"><path d="{traco}"/></svg>')
