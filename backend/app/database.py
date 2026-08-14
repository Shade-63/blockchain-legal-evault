from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings

# Concrete engine setup
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def check_db_connection() -> tuple[bool, str | None]:
    """
    Checks connection to the configured PostgreSQL database.
    Does NOT silently fall back to a mock/sqlite/in-memory DB.
    """
    try:
        # Obtain a connection and execute a simple query
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            return True, None
    except Exception as e:
        return False, str(e)
