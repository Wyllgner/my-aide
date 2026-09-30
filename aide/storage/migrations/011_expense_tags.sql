-- Tag: de onde foi o gasto, dentro de uma categoria.
--
-- "10 em farmácia" consome o teto de `pessoal` e continua dizendo que foi
-- farmácia. A tag pertence a uma categoria só, e é a categoria que conta para
-- o teto: somar a tag de novo contaria o mesmo real duas vezes.
--
-- `key` é a tag sem acento e em minúsculo, para "farmacia" achar "farmácia";
-- `tag` guarda como a pessoa escreveu, que é como a tela mostra.

CREATE TABLE expense_tags (
    key         TEXT PRIMARY KEY,
    tag         TEXT NOT NULL,
    category    TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

ALTER TABLE expenses ADD COLUMN tag TEXT;
