from contextvars import ContextVar

from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_size=10,
    max_overflow=20
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Wer arbeitet gerade (E-Mail aus dem Login-Token, gesetzt in main.py je Anfrage). Steht in jeder Transaktion als
# seda.app_benutzer bereit - das Protokoll der Monatssperre (migrations/monatssperre.sql) schreibt es zu jeder Aenderung.
APP_BENUTZER: ContextVar = ContextVar("app_benutzer", default=None)


@event.listens_for(Session, "after_begin")
def _app_benutzer_setzen(session, transaction, connection):
    wer = APP_BENUTZER.get()
    if wer:
        connection.exec_driver_sql("SELECT set_config('seda.app_benutzer', %(w)s, true)", {"w": wer[:200]})

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
