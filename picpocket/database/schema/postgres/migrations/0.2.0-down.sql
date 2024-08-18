ALTER TABLE tags DROP COLUMN exemplar;

INSERT INTO version (version) VALUES (ROW(0, 1, 0, NULL));