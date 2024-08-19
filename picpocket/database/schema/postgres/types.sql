DO $$ BEGIN
    CREATE TYPE version_number AS (
        major INTEGER,
        minor INTEGER,
        patch INTEGER,
        label TEXT
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;
