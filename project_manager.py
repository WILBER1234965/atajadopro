from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import mkdtemp
from zipfile import ZipFile, ZIP_DEFLATED
from shutil import copy2, rmtree
import sqlite3

from PyQt6.QtCore import QObject, pyqtSignal

from database import Database, IMAGES_DIR


@dataclass
class Proyecto:
    """Representa un proyecto activo."""
    db: Database
    path: Path | None = None


class TrackedDatabase(Database):
    """Subclase que avisa al manager cuando se modifica la base."""

    def __init__(self, manager: 'ProyectoManager', db_file: str | Path = ":memory:"):
        self._manager = manager
        super().__init__(db_file)

    def execute(self, sql: str, params=()):
        result = super().execute(sql, params)
        cmd = sql.strip().split()[0].upper()
        if cmd in {"INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER", "REPLACE"}:
            self._manager.mark_modified()
        return result


class ProyectoManager(QObject):
    """Gestiona apertura, guardado y estado del proyecto actual."""

    dirtyChanged = pyqtSignal(bool)
    pathChanged = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._dirty = False
        self._temp_dir: Path | None = None
        self.proyecto = Proyecto(TrackedDatabase(self))

    # ------------------------------------------------------------------
    # Propiedades
    # ------------------------------------------------------------------
    @property
    def is_dirty(self) -> bool:
        return self._dirty

    # ------------------------------------------------------------------
    def mark_modified(self):
        if not self._dirty:
            self._dirty = True
            self.dirtyChanged.emit(True)

    # ------------------------------------------------------------------
    def new_project(self):
        self._cleanup()
        self.proyecto = Proyecto(TrackedDatabase(self))
        self._dirty = False
        self.pathChanged.emit("")
        self.dirtyChanged.emit(False)

    # ------------------------------------------------------------------
    def open_project(self, path: str | Path):
        self._cleanup()
        path = Path(path)
        tmp_dir = Path(mkdtemp(prefix="proj_"))
        with ZipFile(path) as z:
            z.extractall(tmp_dir)
        db_path = tmp_dir / "atajados.db"
        if not db_path.exists():
            rmtree(tmp_dir, ignore_errors=True)
            raise FileNotFoundError("El paquete no contiene atajados.db")
        self.proyecto = Proyecto(TrackedDatabase(self, db_path), path)
        self._temp_dir = tmp_dir
        self._dirty = False
        self.pathChanged.emit(str(path))
        self.dirtyChanged.emit(False)

    # ------------------------------------------------------------------
    def save_project(self, path: str | Path | None = None) -> bool:
        if path is None:
            if not self.proyecto.path:
                return False
            path = self.proyecto.path
        path = Path(path)

        tmp_db = path.with_suffix(".tmpdb")
        if self.proyecto.db.db_path == ":memory:":
            with sqlite3.connect(tmp_db) as dest:
                for line in self.proyecto.db.conn.iterdump():
                    if line not in ("BEGIN;", "COMMIT;"):
                        dest.execute(line)
        else:
            copy2(self.proyecto.db.db_path, tmp_db)

        with ZipFile(path, "w", ZIP_DEFLATED) as z:
            z.write(tmp_db, "atajados.db")
            if IMAGES_DIR.exists():
                for img in IMAGES_DIR.rglob("*"):
                    if img.is_file():
                        z.write(img, Path("images") / img.relative_to(IMAGES_DIR))
        tmp_db.unlink(missing_ok=True)

        self.proyecto.path = path
        self._dirty = False
        self.pathChanged.emit(str(path))
        self.dirtyChanged.emit(False)
        return True

    # ------------------------------------------------------------------
    def _cleanup(self):
        if self._temp_dir and self._temp_dir.exists():
            rmtree(self._temp_dir, ignore_errors=True)
            self._temp_dir = None

    def __del__(self):
        self._cleanup()