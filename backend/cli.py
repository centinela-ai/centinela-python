"""Centinela backend admin CLI.

    python cli.py create-org "Acme"
    python cli.py create-key <org-id-or-name> "prod key"   # prints key ONCE
    python cli.py revoke-key <api-key-id>
    python cli.py cleanup --older-than-days 7
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import typer
from sqlalchemy import delete, func, or_, select

from app.db import SessionLocal
from app.models import ApiKey, Event, Org
from app.security import generate_key

app = typer.Typer(add_completion=False, help="Centinela backend administration.")


def _resolve_org(db, org_ref: str) -> Org:
    org: Org | None = None
    try:
        org = db.get(Org, uuid.UUID(org_ref))
    except (ValueError, AttributeError):
        org = None
    if org is None:
        org = db.execute(select(Org).where(Org.name == org_ref)).scalar_one_or_none()
    if org is None:
        typer.secho(f"Org not found: {org_ref}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    return org


@app.command("create-org")
def create_org(name: str) -> None:
    """Create an organization."""
    with SessionLocal() as db:
        org = Org(name=name)
        db.add(org)
        db.commit()
        typer.secho(f"Created org '{name}'", fg=typer.colors.GREEN)
        typer.echo(f"  id: {org.id}")


@app.command("create-key")
def create_key(org: str, name: str) -> None:
    """Create an API key for an org. The key is printed only once."""
    with SessionLocal() as db:
        org_row = _resolve_org(db, org)
        generated = generate_key()
        db.add(
            ApiKey(
                org_id=org_row.id,
                name=name,
                key_prefix=generated.prefix,
                key_hash=generated.key_hash,
                salt=generated.salt,
            )
        )
        db.commit()
        typer.secho(
            f"Created key '{name}' for org '{org_row.name}'.", fg=typer.colors.GREEN
        )
        typer.secho(
            "Store this key now — it will not be shown again:",
            fg=typer.colors.YELLOW,
        )
        typer.echo(generated.full_key)


@app.command("revoke-key")
def revoke_key(key_id: str) -> None:
    """Revoke an API key by its id."""
    with SessionLocal() as db:
        try:
            row = db.get(ApiKey, uuid.UUID(key_id))
        except ValueError:
            row = None
        if row is None:
            typer.secho(f"API key not found: {key_id}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
        if row.revoked_at is not None:
            typer.secho("Key already revoked.", fg=typer.colors.YELLOW)
            raise typer.Exit(code=0)
        row.revoked_at = datetime.now(timezone.utc)
        db.commit()
        typer.secho(f"Revoked key {key_id}", fg=typer.colors.GREEN)


@app.command("cleanup")
def cleanup(older_than_days: int = typer.Option(..., "--older-than-days")) -> None:
    """Delete events older than the retention window (in days)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    with SessionLocal() as db:
        before = db.execute(
            select(func.count()).select_from(Event).where(Event.timestamp < cutoff)
        ).scalar_one()
        db.execute(delete(Event).where(Event.timestamp < cutoff))
        db.commit()
        typer.secho(
            f"Deleted {before} events older than {older_than_days} days "
            f"(before {cutoff.isoformat()}).",
            fg=typer.colors.GREEN,
        )


if __name__ == "__main__":
    app()
