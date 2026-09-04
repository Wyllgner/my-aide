-- Vetores das notas. Ficou de fora da 001 por engano.
-- BLOB de float32 empacotado: o volume de um vault pessoal não justifica
-- um banco vetorial, e busca por força bruta roda em milissegundos.

CREATE TABLE embeddings (
    id         INTEGER PRIMARY KEY,
    ref_type   TEXT NOT NULL,
    ref_id     INTEGER NOT NULL,
    chunk      TEXT NOT NULL,
    vector     BLOB NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX idx_embeddings_ref ON embeddings (ref_type, ref_id);
