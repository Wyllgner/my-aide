-- Todo gasto é débito ou crédito.
--
-- A coluna `method` já existia como texto livre ("pix, crédito, débito,
-- dinheiro") e nunca foi preenchida. Texto livre não soma: "crédito", "credito"
-- e "cartão" viram três grupos. Daqui em diante ela só guarda `debito` ou
-- `credito`, e o que não foi dito é débito — pix e dinheiro saem da conta na
-- hora, que é o que débito quer dizer aqui.

UPDATE expenses SET method = 'credito'
 WHERE lower(method) IN ('credito', 'crédito', 'cartão de crédito', 'cartao de credito');
UPDATE expenses SET method = 'debito'
 WHERE method IS NULL OR method <> 'credito';
