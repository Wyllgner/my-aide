-- Liga cada chamada de LLM à conversa e à volta que a provocou.
--
-- Sem isto dá para saber quanto o assessor custou no mês, mas não quanto
-- custou *aquela* pergunta — e é a segunda que ensina alguma coisa, porque
-- mostra qual jeito de perguntar sai caro.
--
-- `turn_id` é o id da mensagem do usuário que abriu a volta: uma pergunta
-- pode gerar várias chamadas (o laço de tools), e todas pertencem a ela.

ALTER TABLE llm_usage ADD COLUMN session_id TEXT;
ALTER TABLE llm_usage ADD COLUMN turn_id INTEGER;

CREATE INDEX idx_llm_usage_turno ON llm_usage (turn_id);
