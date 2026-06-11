"""initial schema: orgs, api_keys, partitioned events

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-11

The ``events`` table is RANGE-partitioned by month on ``timestamp``. SQLAlchemy
cannot emit ``PARTITION BY``, so the parent table and partitions are created
with raw SQL below.

Creating future partitions
--------------------------
This migration provisions monthly partitions for 2025-01 .. 2027-12 plus a
catch-all ``events_default``. To add another month manually::

    CREATE TABLE events_2028_01 PARTITION OF events
        FOR VALUES FROM ('2028-01-01+00') TO ('2028-02-01+00');

Or add a follow-up Alembic revision that loops the same way this one does.
The ``events_default`` partition guarantees inserts never fail for timestamps
outside the provisioned range; rebalance out of it when adding real partitions.
"""

from __future__ import annotations

from datetime import date

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

# Provisioned monthly partition window [start, end).
_PARTITION_START = date(2025, 1, 1)
_PARTITION_END = date(2028, 1, 1)


def _months(start: date, end: date):
    y, m = start.year, start.month
    while date(y, m, 1) < end:
        cur = date(y, m, 1)
        if m == 12:
            nxt = date(y + 1, 1, 1)
        else:
            nxt = date(y, m + 1, 1)
        yield cur, nxt
        y, m = nxt.year, nxt.month


def upgrade() -> None:
    op.create_table(
        "orgs",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "api_keys",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("key_prefix", sa.String(), nullable=False),
        sa.Column("key_hash", sa.String(), nullable=False),
        sa.Column("salt", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_api_keys_org_id", "api_keys", ["org_id"])
    op.create_index("ix_api_keys_key_prefix", "api_keys", ["key_prefix"], unique=True)

    # Partitioned parent table.
    op.execute(
        """
        CREATE TABLE events (
            id UUID NOT NULL DEFAULT gen_random_uuid(),
            "timestamp" TIMESTAMPTZ NOT NULL,
            org_id UUID NOT NULL,
            trace_id TEXT NOT NULL,
            span_id TEXT,
            parent_span_id TEXT,
            project TEXT,
            type TEXT NOT NULL,
            name TEXT,
            status TEXT NOT NULL DEFAULT 'ok',
            duration_ms INTEGER NOT NULL DEFAULT 0,
            payload JSONB NOT NULL,
            received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id, "timestamp")
        ) PARTITION BY RANGE ("timestamp");
        """
    )
    op.execute('CREATE INDEX ix_events_org_trace ON events (org_id, trace_id);')
    op.execute('CREATE INDEX ix_events_org_ts ON events (org_id, "timestamp");')
    op.execute('CREATE INDEX ix_events_timestamp ON events ("timestamp");')

    # Monthly partitions + catch-all default.
    for start, nxt in _months(_PARTITION_START, _PARTITION_END):
        name = f"events_{start.year}_{start.month:02d}"
        op.execute(
            f"CREATE TABLE {name} PARTITION OF events "
            f"FOR VALUES FROM ('{start.isoformat()}+00') TO ('{nxt.isoformat()}+00');"
        )
    op.execute("CREATE TABLE events_default PARTITION OF events DEFAULT;")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS events CASCADE;")
    op.drop_index("ix_api_keys_key_prefix", table_name="api_keys")
    op.drop_index("ix_api_keys_org_id", table_name="api_keys")
    op.drop_table("api_keys")
    op.drop_table("orgs")
