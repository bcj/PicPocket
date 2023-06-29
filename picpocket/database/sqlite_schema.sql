CREATE TABLE IF NOT EXISTS version (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    major INTEGER NOT NULL,
    minor INTEGER NOT NULL,
    patch INTEGER NOT NULL,
    label TEXT
) STRICT;

-- sqlite doesn't have a boolean type and if we use STRICT, we can't label
-- the column type as bool
CREATE TABLE IF NOT EXISTS locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    -- allowing this to be nullable because removable storage may not
    -- always be mounted to the same location
    path TEXT,
    source INTEGER DEFAULT false,
    destination INTEGER DEFAULT false,
    removable INTEGER DEFAULT false
) STRICT;

CREATE TABLE IF NOT EXISTS tasks (
    name TEXT PRIMARY KEY,
    description TEXT,
    source INTEGER NOT NULL REFERENCES locations (id) ON DELETE CASCADE,
    destination INTEGER NOT NULL REFERENCES locations (id) ON DELETE CASCADE,
    configuration TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS task_invocations (
    task TEXT PRIMARY KEY REFERENCES tasks (name) ON DELETE CASCADE,
    last_ran INTEGER
) STRICT;

CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hash TEXT NOT NULL,
    creation_date INTEGER NOT NULL,
    last_modified INTEGER NOT NULL,
    name TEXT NOT NULL,
    extension TEXT NOT NULL,
    width INTEGER,
    height INTEGER,
    creator TEXT,
    -- we'll prevent people accidentally deleting their own data at an API level
    location INTEGER NOT NULL REFERENCES locations (id) ON DELETE CASCADE,
    path TEXT NOT NULL,  -- relative to location
    title TEXT,
    caption TEXT,
    alt TEXT,
    rating INTEGER, -- TODO, think if we want to restrict size
    exif TEXT NOT NULL,  -- json-encoded
    UNIQUE (location, path)
) STRICT;

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE,
    escaped_name TEXT UNIQUE,
    depth INTEGER NOT NULL,
    description TEXT
) STRICT;

CREATE TABLE IF NOT EXISTS image_tags (
    image INTEGER NOT NULL REFERENCES images (id) ON DELETE CASCADE,
    tag INTEGER NOT NULL REFERENCES tags (id) ON DELETE CASCADE,
    PRIMARY KEY (image, tag)
) STRICT;

CREATE TABLE IF NOT EXISTS session_info (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    expires INTEGER NOT NULL,
    data TEXT NOT NULL
) STRICT;