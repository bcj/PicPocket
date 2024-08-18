ALTER TABLE tags DROP COLUMN exemplar;

INSERT INTO version (major, minor, patch, label) VALUES (0, 1, 0, NULL);