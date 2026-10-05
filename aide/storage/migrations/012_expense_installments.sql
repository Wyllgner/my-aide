-- Compra parcelada: uma linha por parcela, cada uma no mês em que cai.
--
-- A soma do mês e o teto olham `spent_at`, então a parcela de março consome o
-- teto de março, que é quando o dinheiro sai. Lançar a compra inteira no dia
-- estouraria o teto de um mês só e deixaria os outros limpos.
--
-- `installment_group` é o id da primeira parcela, e liga as outras a ela.
-- Gasto à vista deixa as três colunas nulas.

ALTER TABLE expenses ADD COLUMN installment_group INTEGER;
ALTER TABLE expenses ADD COLUMN installment INTEGER;
ALTER TABLE expenses ADD COLUMN installments INTEGER;

CREATE INDEX idx_expenses_installment_group ON expenses (installment_group);
