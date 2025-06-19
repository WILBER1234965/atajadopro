"""Simple SQLite wrapper used by the application."""

from pathlib import Path
import os, sqlite3
from contextlib import closing

# ------------ Rutas por defecto ------------ #
DB_FILE     = Path("data") / "atajados.db"   # Base de datos por defecto en disco
PHOTO_DIR   = Path("photos")
IMAGES_DIR  = Path("data/images")

# Crea carpetas necesarias
for d in (PHOTO_DIR, IMAGES_DIR):
    d.mkdir(parents=True, exist_ok=True)
# ------------------------------------------- #


class Database:
    """SQLite database connection with helper methods."""

    def __init__(self, db_file: str | Path = DB_FILE):
        # -------- MODO MEMORIA ------------------------------------------------ #
        if db_file == ":memory:":
            self.db_path = ":memory:"              # cadena especial SQLite
            self.conn = sqlite3.connect(":memory:")
            self.init_tables()
            return
        # ---------------------------------------------------------------------- #

        # -------- MODO ARCHIVO EN DISCO --------------------------------------- #
        self.db_path = Path(db_file).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.init_tables()
        # ---------------------------------------------------------------------- #

    # ---------- Reabrir otra base de datos ---------- #
    def open(self, new_file: str | Path) -> None:
        """Reabrir conexión a otro archivo .db o a ':memory:'."""
        self.close()

        if new_file == ":memory:":
            self.db_path = ":memory:"
            self.conn = sqlite3.connect(":memory:")
        else:
            self.db_path = Path(new_file).resolve()
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(self.db_path)

        self.init_tables()

    # ---------- Cerrar conexión ---------- #
    def close(self) -> None:
        if getattr(self, "conn", None):
            self.conn.close()
            self.conn = None

    # ---------- Crear tablas si no existen ---------- #
    def init_tables(self) -> None:
        with closing(self.conn.cursor()) as c:
            # Tabla items
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS items (
                    id INTEGER PRIMARY KEY,
                    name TEXT,
                    unit TEXT,
                    total REAL,
                    incidence REAL,
                    active INTEGER DEFAULT 0,
                    progress REAL DEFAULT 0
                )
                """
            )
            # Compatibilidad columna progress
            cols = [r[1] for r in c.execute("PRAGMA table_info(items)")]
            if "progress" not in cols:
                c.execute("ALTER TABLE items ADD COLUMN progress REAL DEFAULT 0")

            # Tabla atajados
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS atajados (
                    id INTEGER PRIMARY KEY,
                    number INTEGER,
                    comunidad TEXT,
                    beneficiario TEXT,
                    ci TEXT,
                    coord_e REAL,
                    coord_n REAL,
                    start_date TEXT,
                    end_date TEXT,
                    status TEXT,
                    observations TEXT,
                    photo TEXT
                )
                """
            )

            # Tabla avances
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS avances (
                    id INTEGER PRIMARY KEY,
                    atajado_id INTEGER,
                    item_id INTEGER,
                    date TEXT,
                    quantity REAL,
                    start_date TEXT,
                    end_date TEXT
                )
                """
            )

            # Tabla cronograma
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS cronograma (
                    id INTEGER PRIMARY KEY,
                    hito TEXT NOT NULL,
                    date TEXT NOT NULL,
                    obs TEXT
                )
                """
            )

            self.conn.commit()

    # ---------- Helpers CRUD ---------- #
    def fetchall(self, sql: str, params: tuple = ()):
        with closing(self.conn.cursor()) as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def execute(self, sql: str, params: tuple = ()):
        with closing(self.conn.cursor()) as cur:
            cur.execute(sql, params)
            self.conn.commit()

    # ---------- Avance ponderado del proyecto ---------- #
    def get_project_progress(self) -> float:
        rows = self.fetchall(
            "SELECT id, total, incidence, active, progress FROM items"
        )
        if not rows:
            return 0.0

        total_cost = executed = 0.0
        for iid, qty, pu, active, prog in rows:
            cost = qty * pu
            total_cost += cost
            # Si el ítem está activo, usa el porcentaje real de avances
            pct = (
                self.fetchall(
                    "SELECT AVG(quantity) FROM avances WHERE item_id=?", (iid,)
                )[0][0]
                or 0.0
            ) if active else (prog or 0.0)
            executed += (pct / 100.0) * cost

        return (executed / total_cost * 100.0) if total_cost else 0.0
