"""O que a tela Arquivos faz com os arquivos: converter e organizar PDF.

Nada aqui guarda coisa alguma: cada função recebe caminhos de entrada numa
pasta temporária e escreve o resultado em outra. Quem cria e apaga as pastas
é a rota.
"""

# o que um pedido da tela pode trazer, somando todos os arquivos
TAMANHO_MAXIMO = 200 * 1024 * 1024
MAXIMO_DE_ARQUIVOS = 50
# a linha do plano que abre o pedido: a lista de páginas cabe com folga
PLANO_MAXIMO = 256 * 1024
