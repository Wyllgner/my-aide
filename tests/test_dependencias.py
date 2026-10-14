"""A trava de dependências: toda dependência declarada travada, com hash."""

import re
import tomllib
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def _nome(especificacao: str) -> str:
    return re.split(r"[<>=!~\[; ]", especificacao, maxsplit=1)[0].lower().replace("_", "-")


def _travados() -> dict[str, list[str]]:
    texto = (RAIZ / "requirements.lock").read_text()
    travados: dict[str, list[str]] = {}
    for bloco in re.split(r"\n(?=[A-Za-z0-9])", texto):
        cabeca = re.match(r"([A-Za-z0-9_.-]+)==(\S+)", bloco)
        if cabeca:
            travados[cabeca.group(1).lower().replace("_", "-")] = re.findall(
                r"--hash=sha256:([0-9a-f]{64})", bloco)
    return travados


def test_toda_dependencia_declarada_esta_travada():
    projeto = tomllib.loads((RAIZ / "pyproject.toml").read_text())["project"]
    declaradas = {_nome(d) for d in projeto["dependencies"]}
    for extra in projeto["optional-dependencies"].values():
        declaradas |= {_nome(d) for d in extra}
    faltando = declaradas - set(_travados())
    assert not faltando, f"rode deploy/travar_dependencias.py; faltam: {sorted(faltando)}"


def test_todo_pacote_travado_tem_hash():
    """Sem hash, --require-hashes recusa a instalação inteira; com hash
    errado, recusa o pacote adulterado."""
    sem_hash = [nome for nome, hashes in _travados().items() if not hashes]
    assert not sem_hash
    assert len(_travados()) > 20  # diretos e indiretos, não só os declarados
