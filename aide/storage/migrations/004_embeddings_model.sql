-- Guarda o modelo que gerou cada vetor.
--
-- Sem isto, trocar o modelo de embedding quebra a busca em silêncio: a dimensão
-- do vetor muda, `similaridade()` devolve 0.0 para tamanhos diferentes, e a
-- busca semântica passa a não achar nada — sem erro, sem aviso. O sintoma é o
-- assessor "esquecer" as notas.
--
-- O backfill afirma o que de fato aconteceu: `MODELO_PADRAO` sempre foi
-- text-embedding-3-small e nunca houve como configurar outro, então todo vetor
-- que existe hoje veio dele.

ALTER TABLE embeddings ADD COLUMN model TEXT;

UPDATE embeddings SET model = 'text-embedding-3-small' WHERE model IS NULL;
