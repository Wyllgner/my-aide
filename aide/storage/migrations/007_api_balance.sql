-- Saldo da API, anotado à mão.
--
-- A OpenAI não expõe saldo por API: os endpoints de billing exigem a sessão do
-- navegador. Então o saldo entra aqui quando você o lê no painel, e a partir
-- dele o assessor desconta o gasto estimado para dizer quanto deve restar.
--
-- Histórico em vez de um valor só: com duas âncoras dá para conferir se a
-- estimativa está acompanhando a cobrança real ou fugindo dela.

CREATE TABLE api_balance (
    id       INTEGER PRIMARY KEY,
    cents    INTEGER NOT NULL,
    noted_at TEXT    NOT NULL,
    source   TEXT    NOT NULL DEFAULT 'manual'
);
CREATE INDEX idx_api_balance_noted ON api_balance (noted_at DESC);
