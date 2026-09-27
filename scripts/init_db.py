"""
Creates all tables directly from the ORM models. Fine for local demo use;
use Alembic migrations instead once this is a real deployed product (see
README TODO list).

Run: python scripts/init_db.py
"""

from sqlalchemy import text

from app.models.db import Base
from app.models.session import engine

if __name__ == "__main__":
    # pgvector ships as a Postgres extension, not a built-in type — even
    # on the pgvector/pgvector:pg16 image, it must be explicitly enabled
    # per-database before VECTOR columns can be created.
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    print("pgvector extension enabled.")

    Base.metadata.create_all(engine)
    print("Tables created.")