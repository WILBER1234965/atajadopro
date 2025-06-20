"""Database layer para la aplicación Atajados.

- Maneja conexión SQLite.
- Auto-crea tablas si no existen.
- Ejecuta migraciones incrementales para mantener compatibilidad
  con versiones anteriores.
- Provee helpers `fetchone`, `fetchall`, `execute`, `get_project_progress`.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Iterable

# ────────────────────────────────────────────────────────────
# Rutas por defecto
# ────────────────────────────────────────────────────────────
DB_FILE   = Path("data") / "atajados.db"
PHOTO_DIR = Path("photos")
IMAGES_DIR = Path("data/images")

for d in (PHOTO_DIR, IMAGES_DIR):
    d.mkdir(parents=True, exist_ok=True)


# ────────────────────────────────────────────────────────────
# Clase envoltorio
# ────────────────────────────────────────────────────────────
class Database:
    """Envoltorio liviano sobre *sqlite3* con migraciones implícitas."""

    def __init__(self, db_file: str | Path = DB_FILE) -> None:
        self.open(db_file)

    # ─────────────────────────────────────────────── abrir / cerrar
    def open(self, db_file: str | Path) -> None:
        """Abre (o re-abre) la conexión y garantiza esquema actualizado."""
        if getattr(self, "conn", None):
            self.conn.close()

        if db_file == ":memory:":
            self.db_path = ":memory:"
            self.conn = sqlite3.connect(":memory:")
        else:
            self.db_path = Path(db_file).resolve()
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(self.db_path)

        # Forzar claves foráneas
        self.conn.execute("PRAGMA foreign_keys = ON")

        self._init_tables()
        self._migrations()

    def close(self) -> None:
        if getattr(self, "conn", None):
            self.conn.close()
            self.conn = None

    # ─────────────────────────────────────────────── helpers SQL
    def fetchone(self, sql: str, params: Iterable[Any] = ()) -> tuple | None:
        with closing(self.conn.cursor()) as cur:
            cur.execute(sql, params)
            return cur.fetchone()

    def fetchall(self, sql: str, params: Iterable[Any] = ()) -> list[tuple]:
        with closing(self.conn.cursor()) as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def execute(self, sql: str, params: Iterable[Any] = ()) -> None:
        with closing(self.conn.cursor()) as cur:
            cur.execute(sql, params)
            self.conn.commit()

    # ─────────────────────────────────────────────── creación básica
    def _init_tables(self) -> None:
        """Crea tablas mínimas si todavía no existen."""
        with closing(self.conn.cursor()) as c:
            # Ítems
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS items(
                    id          INTEGER PRIMARY KEY,
                    code        TEXT DEFAULT '',
                    name        TEXT,
                    unit        TEXT,
                    total       REAL,
                    unit_price  REAL DEFAULT 0,
                    incidence   REAL DEFAULT 0,     -- retro-compatibilidad
                    active      INTEGER DEFAULT 0,
                    progress    REAL DEFAULT 0
                )
            """
            )

            # Atajados
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS atajados(
                    id           INTEGER PRIMARY KEY,
                    number       INTEGER UNIQUE,
                    comunidad    TEXT,
                    beneficiario TEXT,
                    ci           TEXT,
                    coord_e      REAL,
                    coord_n      REAL,
                    este         REAL,              -- alias coord_e
                    norte        REAL,              -- alias coord_n
                    start_date   TEXT,
                    end_date     TEXT,
                    status       TEXT,
                    observations TEXT,
                    photo        TEXT
                )
            """
            )

            # Avances
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS avances(
                    id           INTEGER PRIMARY KEY,
                    atajado_id   INTEGER,
                    item_id      INTEGER,
                    date         TEXT,
                    quantity     REAL,              -- % (0-100)
                    start_date   TEXT,
                    end_date     TEXT,
                    FOREIGN KEY(atajado_id) REFERENCES atajados(id) ON DELETE CASCADE,
                    FOREIGN KEY(item_id)    REFERENCES items(id)    ON DELETE CASCADE
                )
            """
            )

            # Cronograma
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS cronograma(
                    id   INTEGER PRIMARY KEY,
                    hito TEXT NOT NULL,
                    date TEXT NOT NULL,
                    obs  TEXT
                )
            """
            )

            self.conn.commit()

    # ─────────────────────────────────────────────── migraciones
    def _column_exists(self, table: str, column: str) -> bool:
        cur = self.conn.execute(f"PRAGMA table_info({table})")
        return any(col[1] == column for col in cur.fetchall())

    def _migrations(self) -> None:
        """Aplica migraciones incrementales para alinear la BD con el código."""
        with closing(self.conn.cursor()) as c:
            # items.code
            if not self._column_exists("items", "code"):
                c.execute("ALTER TABLE items ADD COLUMN code TEXT DEFAULT ''")

            # items.unit_price (nuevo) – copiar desde incidence si existe
            if not self._column_exists("items", "unit_price"):
                c.execute("ALTER TABLE items ADD COLUMN unit_price REAL DEFAULT 0")
                if self._column_exists("items", "incidence"):
                    c.execute("UPDATE items SET unit_price = incidence")

            # atajados.este y norte
            if not self._column_exists("atajados", "este"):
                c.execute("ALTER TABLE atajados ADD COLUMN este REAL")
                c.execute("UPDATE atajados SET este = coord_e")
            if not self._column_exists("atajados", "norte"):
                c.execute("ALTER TABLE atajados ADD COLUMN norte REAL")
                c.execute("UPDATE atajados SET norte = coord_n")

        self.conn.commit()

    # ─────────────────────────────────────────────── lógica agregada
    def get_project_progress(self) -> float:
        """Devuelve el avance ponderado global (0-100 %)."""
        rows = self.fetchall(
            """
            SELECT id,
                   total,
                   COALESCE(unit_price, incidence, 0) AS pu,
                   active,
                   progress
            FROM items
            """
        )
        if not rows:
            return 0.0

        total_cost = executed = 0.0
        for iid, qty, pu, active, prog in rows:
            cost = qty * pu
            total_cost += cost

            if active:
                pct = self.fetchone(
                    "SELECT COALESCE(AVG(quantity), 0) FROM avances WHERE item_id = ?", (iid,)
                )[0]
            else:
                pct = prog or 0.0

            executed += (pct / 100.0) * cost

        return (executed / total_cost * 100.0) if total_cost else 0.0
