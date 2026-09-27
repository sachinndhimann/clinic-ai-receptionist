"""
Engine + session factory. Kept separate from db.py (which only defines
the ORM models) so models can be imported without pulling in a live DB
connection, e.g. from scripts that just need the Base metadata.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import settings

engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_session() -> Session:
    """Plain factory for scripts (seed, migrations helpers) — caller closes it."""
    return SessionLocal()
