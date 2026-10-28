// As notas. Arquivo, e nao <script> embutido, porque a CSP so deixa rodar
// script vindo daqui (script-src 'self'): um <script> que um dia escapasse
// do escape de uma tela nao roda. Sem framework e sem build.
//
// Faz so o que o servidor nao consegue: salvar enquanto voce digita, avisar
// do conflito com quem escreveu por fora, e os botoes de criar e apagar.
//
// Uma parte por assunto, em js/notas/. Importar uma parte liga ela: o corpo
// dela roda na hora, como rodava quando isto era um arquivo so, e por isso
// estas linhas estao na ordem de antes.
import "/js/notas/arvore.js";
import "/js/notas/criar.js";
import "/js/notas/abrir-rapido.js";
import "/js/notas/quebrados.js";
import "/js/notas/pastas.js";
import "/js/notas/grafo.js";
import "/js/notas/editor.js";
