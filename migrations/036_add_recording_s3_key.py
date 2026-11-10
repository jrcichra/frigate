"""Peewee migrations -- 036_add_recording_s3_key.py."""

import peewee as pw

SQL = pw.SQL


def add_column(migrator, database, table, column, definition):
    # skip if the column already exists, for example from a future upstream change
    columns = [c.name for c in database.get_columns(table)]

    if column not in columns:
        migrator.sql(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {definition}')


def migrate(migrator, database, fake=False, **kwargs):
    add_column(migrator, database, "recordings", "s3_key", "VARCHAR(255) NULL")
    add_column(
        migrator, database, "recordings", "evicted", "INTEGER NOT NULL DEFAULT 0"
    )
    add_column(migrator, database, "export", "s3_key", "VARCHAR(255) NULL")
    add_column(migrator, database, "export", "evicted", "INTEGER NOT NULL DEFAULT 0")


def rollback(migrator, database, fake=False, **kwargs):
    pass
