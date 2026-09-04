-- Índice de texto das notas. O markdown do vault continua sendo a fonte da
-- verdade; isto aqui é índice descartável e reconstruível.
--
-- Tabela FTS5 comum, não `contentless`: contentless não aceita DELETE, e
-- reindexar uma nota editada é operação corriqueira aqui. O texto duplicado
-- custa quase nada no volume de um vault pessoal.

CREATE VIRTUAL TABLE notes_fts USING fts5(title, body);
