"""The WAL file shrinks back after a checkpoint reset (#131)."""

import sqlite3

from sqlalchemy import create_engine, event

from db.database import WAL_SIZE_LIMIT_BYTES, _set_sqlite_pragma


def test_every_connection_limits_the_wal_file(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'intel.db'}")
    event.listen(engine, "connect", _set_sqlite_pragma)
    with engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert conn.exec_driver_sql("PRAGMA journal_size_limit").scalar() == WAL_SIZE_LIMIT_BYTES


def test_wal_file_is_truncated_to_the_limit_after_a_reset(tmp_path):
    path = tmp_path / "intel.db"
    conn = sqlite3.connect(path)
    _set_sqlite_pragma(conn, None)
    conn.execute("PRAGMA journal_size_limit=4096")  # same mechanism, a small limit keeps the test fast
    conn.execute("PRAGMA wal_autocheckpoint=0")
    conn.execute("CREATE TABLE t (x BLOB)")
    with conn:
        conn.executemany("INSERT INTO t VALUES (?)", [(b"x" * 4000,) for _ in range(500)])
    wal = path.with_name("intel.db-wal")
    assert wal.stat().st_size > 1_000_000
    conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
    with conn:
        conn.execute("INSERT INTO t VALUES (x'00')")  # the next write resets the WAL
    conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
    assert wal.stat().st_size <= 4096 * 2
    conn.close()
