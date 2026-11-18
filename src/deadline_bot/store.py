"""Save deadlines in a small SQLite database file."""
import sqlite3
from dataclasses import dataclass

DAY = 24 * 60 * 60


@dataclass
class Deadline:
    id: int
    user_id: int
    channel_id: int
    title: str
    due: int  # Unix timestamp (seconds)
    warned: bool  # has the 24-hour warning been sent?


class Store:
    def __init__(self, path: str = "deadlines.db"):
        self.db = sqlite3.connect(path)
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS deadlines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                due INTEGER NOT NULL,
                warned INTEGER NOT NULL DEFAULT 0
            )"""
        )
        self.db.commit()

    def _rows(self, sql: str, *args) -> list[Deadline]:
        return [Deadline(r[0], r[1], r[2], r[3], r[4], bool(r[5]))
                for r in self.db.execute(sql, args)]

    def add(self, user_id: int, channel_id: int, title: str, due: int, now: int) -> int:
        # Less than a day left? Skip the 24-hour warning.
        warned = due - now <= DAY
        cur = self.db.execute(
            "INSERT INTO deadlines (user_id, channel_id, title, due, warned) VALUES (?, ?, ?, ?, ?)",
            (user_id, channel_id, title, due, int(warned)),
        )
        self.db.commit()
        return cur.lastrowid

    def upcoming(self, user_id: int) -> list[Deadline]:
        return self._rows(
            "SELECT * FROM deadlines WHERE user_id = ? ORDER BY due", user_id)

    def remove(self, deadline_id: int, user_id: int) -> bool:
        """Delete a deadline. Users can only delete their own."""
        cur = self.db.execute(
            "DELETE FROM deadlines WHERE id = ? AND user_id = ?", (deadline_id, user_id))
        self.db.commit()
        return cur.rowcount > 0

    def needing_warning(self, now: int) -> list[Deadline]:
        return self._rows(
            "SELECT * FROM deadlines WHERE warned = 0 AND due - ? <= ?", now, DAY)

    def mark_warned(self, deadline_id: int) -> None:
        self.db.execute("UPDATE deadlines SET warned = 1 WHERE id = ?", (deadline_id,))
        self.db.commit()

    def due_now(self, now: int) -> list[Deadline]:
        return self._rows("SELECT * FROM deadlines WHERE due <= ?", now)

    def delete(self, deadline_id: int) -> None:
        self.db.execute("DELETE FROM deadlines WHERE id = ?", (deadline_id,))
        self.db.commit()
