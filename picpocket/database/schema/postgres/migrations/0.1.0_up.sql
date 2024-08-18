ALTER TABLE tags
ADD COLUMN exemplar INTEGER REFERENCES images (id) ON DELETE SET NULL;

INSERT INTO version (version) VALUES (ROW(0, 2, 0, 'dev'));