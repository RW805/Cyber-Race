"""
Leaderboard storage.

Data collected per race:
    name        -> player-entered name (free text, sanitised/truncated)
    time_secs   -> final time in seconds: 3 laps of driving + any penalties
    penalty_secs-> seconds added for wrong answers (10s each)
    laps        -> laps completed (always 3 for a finished race, but kept for honesty)
    questions_correct / questions_total -> accuracy, for future stats/extensions
    created_at  -> UTC timestamp, auto-set by SQLite

Storage choice: SQLite (a single local file, leaderboard.db).
Why: zero setup (no server to run on a Raspberry Pi), durable across restarts,
     easy to back up (it's just one file), and trivial to query/export to CSV
     later if you want to share results or put them on a web page.

Sharing: nothing leaves the device by default -- this is local-only, which is
the right default for a classroom/kiosk device with kids' names on it. If you
want a shared/online leaderboard across multiple machines, see the note in
README.md ("Extend: networked leaderboard").
"""
import sqlite3
import time
from contextlib import contextmanager

DB_PATH = "leaderboard.db"

# Results live in `race_results` (ranked by time). Older versions of the game
# used a `results` table ranked by points; it's left alone in the file and ignored.

SCHEMA = """
CREATE TABLE IF NOT EXISTS race_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    time_secs REAL NOT NULL,
    penalty_secs REAL NOT NULL DEFAULT 0,
    laps INTEGER NOT NULL,
    questions_correct INTEGER NOT NULL DEFAULT 0,
    questions_total INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
"""


@contextmanager
def _connect(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def sanitise_name(raw_name: str) -> str:
    """Keep names short and printable -- basic hygiene for anything typed on a kiosk."""
    cleaned = "".join(ch for ch in raw_name if ch.isprintable()).strip()
    cleaned = cleaned[:16]  # cap length so it fits on-screen
    return cleaned or "PLAYER"


def add_result(name, time_secs, penalty_secs=0.0, laps=3, questions_correct=0, questions_total=0,
               db_path=DB_PATH):
    name = sanitise_name(name)
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO race_results (name, time_secs, penalty_secs, laps, questions_correct, "
            "questions_total, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, float(time_secs), float(penalty_secs), int(laps), int(questions_correct),
             int(questions_total), time.time()),
        )


def top_results(limit=10, db_path=DB_PATH):
    """Ranked by fastest final time (driving time + penalties)."""
    with _connect(db_path) as conn:
        cur = conn.execute(
            "SELECT name, time_secs, penalty_secs, laps, questions_correct, questions_total, created_at "
            "FROM race_results ORDER BY time_secs ASC LIMIT ?",
            (limit,),
        )
        rows = cur.fetchall()
    return [
        {
            "name": r[0], "time_secs": r[1], "penalty_secs": r[2], "laps": r[3],
            "questions_correct": r[4], "questions_total": r[5], "created_at": r[6],
        }
        for r in rows
    ]


def clear_all(db_path=DB_PATH):
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM race_results")


if __name__ == "__main__":
    # quick sanity check against a throwaway test DB
    test_db = "/tmp/_leaderboard_test.db"
    import os
    if os.path.exists(test_db):
        os.remove(test_db)

    add_result("Alice", time_secs=95.4, penalty_secs=10, questions_correct=2, questions_total=3, db_path=test_db)
    add_result("Bob", time_secs=110.2, penalty_secs=20, questions_correct=1, questions_total=3, db_path=test_db)
    add_result("Cara", time_secs=88.1, penalty_secs=0, questions_correct=3, questions_total=3, db_path=test_db)

    results = top_results(db_path=test_db)
    assert [r["name"] for r in results] == ["Cara", "Alice", "Bob"], "fastest final time should rank first"
    assert results[2]["penalty_secs"] == 20

    long_name = sanitise_name("  this name is way too long for the screen!!  ")
    assert len(long_name) <= 16

    os.remove(test_db)
    print("OK: leaderboard ranking (fastest time incl. penalties) and name sanitising both work.")
