-- Gasto recorrente: assinatura, conta fixa. Uma linha aqui vira um lançamento
-- comum em `expenses` por mês, como a parcela: a soma do mês, o teto e o que
-- está a cair olham `spent_at` e não precisam saber de onde a linha veio.
--
-- `recurring_month` é o mês a que o lançamento pertence, e não muda quando a
-- data é corrigida. O índice único é o que impede lançar o mesmo mês duas
-- vezes, e a linha apagada continua contando: apagar um mês pula aquele mês,
-- ele não volta na próxima geração.

CREATE TABLE expense_recurring (
    id           INTEGER PRIMARY KEY,
    cents        INTEGER NOT NULL,
    description  TEXT NOT NULL,
    category     TEXT,
    tag          TEXT,
    method       TEXT,
    private      INTEGER NOT NULL DEFAULT 0,
    day          INTEGER NOT NULL CHECK (day BETWEEN 1 AND 31),
    start_month  TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    canceled_at  TEXT
);

ALTER TABLE expenses ADD COLUMN recurring_id INTEGER;
ALTER TABLE expenses ADD COLUMN recurring_month TEXT;

CREATE UNIQUE INDEX idx_expenses_recurring_month
    ON expenses (recurring_id, recurring_month) WHERE recurring_id IS NOT NULL;
