from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class Lead(Base):
    __tablename__ = 'leads'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    channel: Mapped[str] = mapped_column(String(16), default='telegram', nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str] = mapped_column(String(64), nullable=False)
    complaint: Mapped[str] = mapped_column(Text, nullable=False)
    preferred_time: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default='new', nullable=False)


class Database:
    def __init__(self, db_url: str) -> None:
        self.engine = create_engine(db_url, future=True)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)

    def create(self) -> None:
        Base.metadata.create_all(self.engine)
