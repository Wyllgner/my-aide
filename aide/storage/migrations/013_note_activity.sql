-- Em que dias cada nota foi mexida.
--
-- O painel de notas contava "atividade" pela data da última modificação do
-- arquivo, e uma nota mexida hoje sumia do dia em que foi escrita. Esta tabela
-- guarda o histórico: uma linha por nota por dia, com quantas vezes ela foi
-- salva — o salvamento automático da página grava a cada pausa na digitação, e
-- uma linha por gravação encheria o banco de nada.
--
-- `caminho` é o relativo ao vault (Pasta/Nota.md), o mesmo da página; `dia` é
-- a data local de quem usa.

CREATE TABLE note_activity (
    caminho TEXT NOT NULL,
    dia     TEXT NOT NULL,
    vezes   INTEGER NOT NULL DEFAULT 1,
    origem  TEXT NOT NULL,
    PRIMARY KEY (caminho, dia)
);
CREATE INDEX idx_note_activity_dia ON note_activity (dia);
