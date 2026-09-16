"""Preparar e conferir a instalação."""

from __future__ import annotations

from rich.table import Table

from aide.comandos.base import app, console, load_config
from aide.storage import connect, migrate
from aide.tools import registry


@app.command()
def init() -> None:
    """Cria o banco e aplica as migrations."""
    config = load_config()
    conn = connect(config.db_path)
    applied = migrate(conn)
    console.print(f"[green]Aplicado:[/] {', '.join(applied)}" if applied
                  else "[dim]Banco já está atualizado.[/]")
    console.print(f"[dim]{config.db_path}[/]")


@app.command()
def doctor() -> None:
    """Confere se o ambiente está pronto."""
    config = load_config()
    key = config.llm.api_key
    checks = [
        ("config.yaml lido", True, config.timezone),
        ("OPENAI_API_KEY", bool(key), "definida" if key else "faltando — veja .env.example"),
        ("banco", config.db_path.exists(), str(config.db_path)),
        ("tools", bool(registry.names()), f"{len(registry.names())} registradas"),
        ("telegram", config.telegram.usable,
         "configurado" if config.telegram.usable
         else "desligado (opcional — veja 'myaide telegram-id')"),
    ]

    # vetor de outro modelo não dá erro: ele só some da busca. Se ninguém
    # perguntar, ninguém descobre — então o doctor pergunta.
    if config.db_path.exists():
        from aide.llm.embeddings import MODELO_PADRAO
        from aide.storage.search import vetores_de_outro_modelo

        conn = connect(config.db_path)
        migrate(conn)
        atrasados = vetores_de_outro_modelo(conn, MODELO_PADRAO)
        total = sum(atrasados.values())
        checks.append((
            "embeddings", not total,
            f"{MODELO_PADRAO}" if not total
            else f"{total} de outro modelo ({', '.join(atrasados)}) — rode `myaide reindexar`",
        ))
        conn.close()

    table = Table(show_header=False, box=None)
    for name, ok, detail in checks:
        table.add_row("[green]ok[/]" if ok else "[red]--[/]", name, f"[dim]{detail}[/]")
    console.print(table)


@app.command()
def tools() -> None:
    """Lista as tools registradas."""
    table = Table(box=None)
    table.add_column("tool", style="cyan")
    table.add_column("segurança", style="dim")
    table.add_column("descrição")
    for name in registry.names():
        tool = registry.get(name)
        table.add_row(name, tool.safety, tool.description.split(".")[0])
    console.print(table)


