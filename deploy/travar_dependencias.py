"""Gera requirements.lock: cada pacote do ambiente com versão exata e hash.

A trava é do ambiente em que a suíte passou, não de uma resolução nova:
`pip freeze` diz o que está instalado, e o PyPI diz o sha256 de cada arquivo
publicado daquela versão (todas as rodas e o código-fonte, para a trava
servir em outra máquina ou outro Python).

Instalar com a trava — nada entra sem bater o hash, nem pacote indireto:

    .venv/bin/pip install --require-hashes -r requirements.lock
    .venv/bin/pip install --no-deps -e .

Atualizar: atualize o ambiente, rode a suíte, e só então

    .venv/bin/python deploy/travar_dependencias.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "requirements.lock"


def instalados() -> list[tuple[str, str]]:
    feito = subprocess.run([sys.executable, "-m", "pip", "freeze", "--exclude-editable", "--all"],
                           capture_output=True, text=True, check=True)
    pacotes = []
    for linha in feito.stdout.splitlines():
        if "==" not in linha or linha.startswith(("-e", "#")):
            continue
        nome, versao = linha.split("==", 1)
        # pip e setuptools são do ambiente, não do projeto
        if nome.lower() not in {"pip", "setuptools", "wheel"}:
            pacotes.append((nome, versao.strip()))
    return sorted(pacotes, key=lambda p: p[0].lower())


def hashes(nome: str, versao: str) -> list[str]:
    url = f"https://pypi.org/pypi/{nome}/{versao}/json"
    with urllib.request.urlopen(url, timeout=30) as resposta:
        dados = json.load(resposta)
    digestos = sorted({arquivo["digests"]["sha256"] for arquivo in dados["urls"]})
    if not digestos:
        raise SystemExit(f"{nome}=={versao} não tem arquivo publicado no PyPI")
    return digestos


def main() -> None:
    linhas = [
        "# Gerado por deploy/travar_dependencias.py — não edite à mão.",
        "# Versão exata e hash de cada pacote (diretos e indiretos) do ambiente",
        "# em que a suíte passou. Instale com:",
        "#   .venv/bin/pip install --require-hashes -r requirements.lock",
        "#   .venv/bin/pip install --no-deps -e .",
        "",
    ]
    for nome, versao in instalados():
        digestos = hashes(nome, versao)
        linhas.append(f"{nome}=={versao} \\")
        linhas.extend(f"    --hash=sha256:{d}" + (" \\" if i < len(digestos) - 1 else "")
                      for i, d in enumerate(digestos))
    SAIDA.write_text("\n".join(linhas) + "\n")
    print(f"{SAIDA.name}: {sum(1 for linha in linhas if '==' in linha)} pacotes")


if __name__ == "__main__":
    main()
