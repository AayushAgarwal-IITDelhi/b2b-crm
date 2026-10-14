import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from exhibition_lead_agent.db.models import Base

DB_PATH = os.environ.get("EXHIBITION_AGENT_DB", "exhibition_lead_agent.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db(db_path: str = None):
    global engine, SessionLocal
    if db_path:
        url = f"sqlite:///{db_path}"
        engine = create_engine(url, echo=False, connect_args={"check_same_thread": False})
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

def get_db() -> Session:
    db = SessionLocal()
    try:
        return db
    finally:
        pass
