from contextlib import contextmanager
from psycopg2.pool import SimpleConnectionPool
from app.config import settings

_pool = None

def _get_pool():
    global _pool
    if _pool is None:
        _pool = SimpleConnectionPool(minconn=1, maxconn=5, dsn=settings.DATABASE_URL)
    return _pool

@contextmanager
def get_sync_db():
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)