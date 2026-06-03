-- Run as a PostgreSQL superuser, for example:
-- psql -U postgres -f scripts/setup-database.sql

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'creativestudioai') THEN
        CREATE ROLE creativestudioai LOGIN PASSWORD 'Baguvix1@';
    ELSE
        ALTER ROLE creativestudioai WITH LOGIN PASSWORD 'Baguvix1@';
    END IF;
END
$$;

SELECT 'CREATE DATABASE creativestudioai OWNER creativestudioai'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'creativestudioai')\gexec

GRANT ALL PRIVILEGES ON DATABASE creativestudioai TO creativestudioai;
