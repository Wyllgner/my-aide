-- Teto por mes.
--
-- Cada linha vale a partir de `month` ('AAAA-MM') ate a proxima linha da
-- mesma categoria. Mudar o teto de novembro grava uma linha de novembro, e
-- outubro continua lendo a dele: o mes que passou nao muda de numero.
--
-- As linhas de antes valiam para todo mes, e continuam valendo assim: entram
-- com '0000-00', que vem antes de qualquer mes.

CREATE TABLE expense_caps_month (
    category    TEXT NOT NULL,
    month       TEXT NOT NULL,
    cents       INTEGER,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (category, month)
);

INSERT INTO expense_caps_month (category, month, cents, updated_at)
    SELECT category, '0000-00', cents, updated_at FROM expense_caps;

DROP TABLE expense_caps;
ALTER TABLE expense_caps_month RENAME TO expense_caps;
