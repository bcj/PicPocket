ALTER TABLE tags
ADD COLUMN exemplar INTEGER REFERENCES images (id) ON DELETE SET NULL;

INSERT INTO version (major, minor, patch, label) VALUES (0, 2, 0, "dev");