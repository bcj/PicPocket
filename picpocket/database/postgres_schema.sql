-- for custom types see types.sql

CREATE TABLE IF NOT EXISTS version (
    id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    version VERSION_NUMBER NOT NULL
);

-- Locations can represent both places to import images from and
-- places to store images imported from elsewhere. At present, the
-- assumption is that these will be accessed through the file system.
-- Future versions may support remote storage or fetching images through
-- other protocols. Watch this space
CREATE TABLE IF NOT EXISTS locations (
    id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    -- allowing this to be nullable because removable storage may not
    -- always be mounted to the same location
    path TEXT,
    source BOOLEAN DEFAULT false,
    destination BOOLEAN DEFAULT false,
    removable BOOLEAN DEFAULT false
);

-- TODO(1.0): Proper pipelines
CREATE TABLE IF NOT EXISTS tasks (
    name TEXT PRIMARY KEY,
    description TEXT,
    source INTEGER NOT NULL REFERENCES locations (id) ON DELETE CASCADE,
    destination INTEGER NOT NULL REFERENCES locations (id) ON DELETE CASCADE,
    configuration JSON NOT NULL
);

CREATE TABLE IF NOT EXISTS task_invocations (
    task TEXT PRIMARY KEY REFERENCES tasks (name) ON DELETE CASCADE,
    last_ran TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    hash CHARACTER (64) NOT NULL,
    -- If exif data can't be read, these values will be the same
    creation_date TIMESTAMP WITH TIME ZONE NOT NULL,
    last_modified TIMESTAMP WITH TIME ZONE NOT NULL,
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
    -- caption_vector TSVECTOR GENERATED ALWAYS AS (
    --     to_tsvector('english', caption)
    -- ) STORED,
    alt TEXT,
    -- alt_vector TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', alt)) STORED,
    rating INTEGER, -- TODO, think if we want to restrict size
    exif JSON NOT NULL,
    UNIQUE (location, path)
);
-- CREATE INDEX IF NOT EXISTS caption_index ON images USING GIN (caption_vector);
-- CREATE INDEX IF NOT EXISTS alt_index ON images USING GIN (alt_vector);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    name TEXT UNIQUE NOT NULL,
    -- TODO (1.0): Holding off on a more elegant version of this until we've
    -- seen how this performs with a ton of tags for everyday tasks.
    escaped_name TEXT UNIQUE,
    depth INTEGER NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS image_tags (
    image INTEGER NOT NULL REFERENCES images (id) ON DELETE CASCADE,
    tag INTEGER NOT NULL REFERENCES tags (id) ON DELETE CASCADE,
    PRIMARY KEY (image, tag)
);

CREATE TABLE IF NOT EXISTS session_info (
    id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    expires TIMESTAMP WITH TIME ZONE NOT NULL,
    data JSON NOT NULL
)