#!/bin/bash
set -e

# Create a BEFORE INSERT trigger on LiteLLM_EndUserTable that assigns the
# default budget_id ('weekly-5-usd') when a row is inserted with NULL or
# empty budget_id. This is database-level enforcement that cannot be bypassed.
#
# Wrapped in a DO block that checks if the table exists first — on a fresh
# deploy LiteLLM hasn't run its migrations yet, so the table won't exist.
# The hourly enforce-budgets.sh cron will recreate the trigger if LiteLLM
# migrations drop and recreate the table later.

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "litellm" <<-'EOSQL'
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'LiteLLM_EndUserTable'
    ) THEN
        CREATE OR REPLACE FUNCTION set_default_budget_id()
        RETURNS TRIGGER AS $func$
        BEGIN
            IF NEW.budget_id IS NULL OR NEW.budget_id = '' THEN
                NEW.budget_id := 'weekly-5-usd';
            END IF;
            RETURN NEW;
        END;
        $func$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS trg_default_budget_id ON "LiteLLM_EndUserTable";
        CREATE TRIGGER trg_default_budget_id
            BEFORE INSERT ON "LiteLLM_EndUserTable"
            FOR EACH ROW
            EXECUTE FUNCTION set_default_budget_id();

        RAISE NOTICE 'Budget trigger created on LiteLLM_EndUserTable';
    ELSE
        RAISE NOTICE 'LiteLLM_EndUserTable does not exist yet — skipping trigger creation';
    END IF;
END
$$;
EOSQL

echo "Budget trigger init script completed"
