#!/bin/bash

# Values for URL come from .env file
DB_URL="postgresql://$POSTGRES_USER:$POSTGRES_PASS@localhost:5432/$POSTGRES_DB"
MIGRATION_DIR="./migrations"

echo "Ensuring schema migrations table exists..."

psql "$DB_URL" -c "
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version     TEXT        PRIMARY KEY,
        applied  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
"

# Checks all migration files and applies them to local database, if any migrations are missing it will fill it in.
for file in $(ls $MIGRATION_DIR/*.sql | sort); do
    version=$(basename "$file" .sql)

    applied=$(psql "$DB_URL" -tAc "SELECT COUNT(*) FROM schema_migrations WHERE version = '$version'")

    if [ "$applied" -eq "0" ]; then
        echo "Applying: $version"
        psql "$DB_URL" -f "$file"

        psql "$DB_URL" -c "INSERT INTO schema_migrations (version, applied) VALUES ('$version', NOW())"
        echo "Applied: $version"
    else
        echo "Skipped (already applied): $version"
    fi
done

echo "Migrations complete."