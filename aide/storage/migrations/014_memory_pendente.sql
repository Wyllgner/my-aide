-- Fato de perfil gravado por um agente de fora (MCP) espera o dono: o perfil
-- vai inteiro em todo prompt, e um agente enganado por uma página da web não
-- pode plantar ali uma "instrução" que fica. `origem` diz quem gravou.
ALTER TABLE memory ADD COLUMN origem TEXT;
ALTER TABLE memory ADD COLUMN pendente INTEGER NOT NULL DEFAULT 0;
