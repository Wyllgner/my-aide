-- Guarda se o evento é de dia inteiro.
--
-- `ical.conflitos()` já ignora evento de dia inteiro, mas a flag era calculada
-- no parse e jogada fora na hora de gravar. Como `events.conflicts` lê do
-- banco, um feriado (00:00 às 00:00 do dia seguinte) passava a se sobrepor a
-- todo compromisso daquele dia — alarme falso em cima de alarme falso.

ALTER TABLE events ADD COLUMN all_day INTEGER NOT NULL DEFAULT 0;
