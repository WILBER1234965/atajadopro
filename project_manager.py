from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from shutil import copy2, rmtree
from tempfile import mkdtemp, NamedTemporaryFile
from zipfile import ZipFile, ZIP_DEFLATED

from PyQt6.QtCore import QObject, pyqtSignal

from database import Database, IMAGES_DIR


# ───────────────────────────
#   Modelo de proyecto
# ───────────────────────────
@dataclass
class Proyecto:
    """Representa un proyecto activo (BD + ruta en disco)."""
    db: Database
    path: Path | None = None


# ───────────────────────────
#   BD con “dirty flag”
# ───────────────────────────
class TrackedDatabase(Database):
    """Subclase que avisa al manager cuando se modifica la base."""

    def __init__(self, manager: "ProyectoManager", db_file: str | Path = ":memory:"):
        self._manager = manager
        super().__init__(db_file)

    def execute(self, sql: str, params=()):
        res = super().execute(sql, params)
        if sql.strip().split(maxsplit=1)[0].upper() in {
            "INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER", "REPLACE"
        }:
            self._manager.mark_modified()
        return res


# ───────────────────────────
#   Manager de Proyectos
# ───────────────────────────
class ProyectoManager(QObject):
    """Gestiona apertura, guardado y estado del proyecto actual."""

    dirtyChanged = pyqtSignal(bool)
    pathChanged = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._dirty = False
        self._temp_dir: Path | None = None
        self.proyecto = Proyecto(TrackedDatabase(self))

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    def mark_modified(self):
        if not self._dirty:
            self._dirty = True
            self.dirtyChanged.emit(True)

    def new_project(self):
        self._cleanup()
        self.proyecto = Proyecto(TrackedDatabase(self))
        self._dirty = False
        self.pathChanged.emit("")
        self.dirtyChanged.emit(False)

    def open_project(self, path: str | Path):
        self._cleanup()
        path = Path(path)
        tmp_dir = Path(mkdtemp(prefix="proj_"))
        with ZipFile(path) as zf:
            zf.extractall(tmp_dir)

        db_path = tmp_dir / "atajados.db"
        if not db_path.exists():
            rmtree(tmp_dir, ignore_errors=True)
            raise FileNotFoundError("El paquete no contiene atajados.db")

        self.proyecto = Proyecto(TrackedDatabase(self, db_path), path)
        self._temp_dir = tmp_dir
        self._dirty = False
        self.pathChanged.emit(str(path))
        self.dirtyChanged.emit(False)

    def save_project(self, path: str | Path | None = None) -> bool:
        """
        Guarda el proyecto en un archivo «.spkg».
        - Si *path* es None y ya hay ruta: sobrescribe.
        - Si *path* es None y NO hay ruta: devuelve False.
        - Si *path* existe: se actualiza y guarda ahí.
        """
        if path is not None:
            self.proyecto.path = Path(path).with_suffix(".spkg")

        if self.proyecto.path is None:
            return False

        target_path: Path = self.proyecto.path

        # 1️⃣ Crear archivo temporal seguro (.tmpdb)
        with NamedTemporaryFile(suffix=".tmpdb", delete=False) as tf:
            tmp_db = Path(tf.name)

        # 2️⃣ Copiar BD al temporal
        if self.proyecto.db.db_path == ":memory:":
            dump_sql = "\n".join(self.proyecto.db.conn.iterdump())
            with sqlite3.connect(tmp_db) as dest:
                dest.executescript(dump_sql)
                dest.commit()
        else:
            self.proyecto.db.conn.commit()
            copy2(self.proyecto.db.db_path, tmp_db)

        # 3️⃣ Empaquetar en .spkg
        with ZipFile(target_path, "w", compression=ZIP_DEFLATED) as zf:
            zf.write(tmp_db, "atajados.db")
            if IMAGES_DIR.exists():
                for img in IMAGES_DIR.rglob("*"):
                    if img.is_file():
                        zf.write(img, Path("images") / img.relative_to(IMAGES_DIR))

        # 4️⃣ Intentar borrar el temporal con reintentos
        for _ in range(4):
            try:
                tmp_db.unlink()
                break
            except PermissionError:
                time.sleep(0.1)  # esperar y reintentar

        # 5️⃣ Señales y estado
        self._dirty = False
        self.pathChanged.emit(str(target_path))
        self.dirtyChanged.emit(False)
        return True

    def _cleanup(self):
        if self._temp_dir and self._temp_dir.exists():
            rmtree(self._temp_dir, ignore_errors=True)
            self._temp_dir = None

    def close(self):
        """Cerrar y limpiar recursos temporales."""
        self._cleanup()
        
    def __del__(self):
        self._cleanup()
