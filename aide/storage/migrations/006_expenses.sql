-- Controle de gastos.
--
-- O valor vai em centavos inteiros, não em REAL. Ponto flutuante não
-- representa 0,10 exatamente, e somar trezentos lançamentos de almoço acumula
-- erro até o total não bater com a conta — o tipo de bug que só aparece no
-- fim do mês, quando você já não sabe qual lançamento está errado.

CREATE TABLE expenses (
    id          INTEGER PRIMARY KEY,
    cents       INTEGER NOT NULL,
    description TEXT    NOT NULL,
    category    TEXT,
    spent_at    TEXT    NOT NULL,
    method      TEXT,
    private     INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    deleted_at  TEXT
);
CREATE INDEX idx_expenses_spent ON expenses (spent_at) WHERE deleted_at IS NULL;
