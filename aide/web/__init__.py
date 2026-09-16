"""Interface web: só leitura, só nesta máquina.

O `criar_app` fica aqui para quem só quer a aplicação; o servidor em thread,
que é o que o daemon usa, vive em `servidor.py`.
"""

from aide.web.app import ENDERECO, PORTA_PADRAO, criar_app

__all__ = ["ENDERECO", "PORTA_PADRAO", "criar_app"]
