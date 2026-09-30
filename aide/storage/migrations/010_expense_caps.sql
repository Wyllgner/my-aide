-- Teto de gasto alterado pela conversa.
--
-- O teto nasce no config, que é arquivo e o assessor não reescreve: regravar o
-- YAML perderia os comentários que explicam cada número. O que for mudado pelo
-- Telegram ou pela CLI mora aqui e vence o config para aquela categoria.
--
-- `cents` NULL é "tirei o teto": sem a linha, o valor do config voltaria.

CREATE TABLE expense_caps (
    category    TEXT PRIMARY KEY,
    cents       INTEGER,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
