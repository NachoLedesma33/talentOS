from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def _build_engine(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True)


settings = get_settings()
engine = _build_engine(str(settings.DATABASE_URL))
SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
)


def get_db() -> Iterator[Session]:
    """Dependencia de FastAPI: abre y cierra la sesión siempre, incluso con excepción."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
