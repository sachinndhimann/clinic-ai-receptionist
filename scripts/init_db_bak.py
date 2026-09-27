"""
Creates all tables directly from the ORM models. Fine for local demo use;
use Alembic migrations instead once this is a real deployed product (see
README TODO list).

Run: python scripts/init_db.py
"""

from app.models.db import Base
from app.models.session import engine

if __name__ == "__main__":
    Base.metadata.create_all(engine)
    print("Tables created.")
