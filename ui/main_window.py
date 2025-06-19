from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from importlib import import_module
from tempfile import mkdtemp
from shutil import copy2, copytree, rmtree
import sqlite3

from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QFileDialog, QMessageBox, QApplication
)

from database import Database, IMAGES_DIR

# ------------------------------------------------------------------ #
_TABS = [
    ("dashboard_tab", "DashboardTab", "Dashboard"),
    ("items_tab",      "ItemsTab",     "Ítems"),
    ("atajados_tab",   "AtajadosTab",  "Atajados"),
    ("avance_tab",     "AvanceTab",    "Avance"),
    ("cronograma_tab", "CronogramaTab","Cronograma"),
    ("summary_tab",    "SummaryTab",   "Resumen"),
]
# ------------------------------------------------------------------ #


class MainWindow(QMainWindow):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db          # conexión actual (RAM al arrancar)
        self.unsaved = True   # False al guardar/abrir
        self.setWindowTitle("Seguimiento de Atajados – Totora")
        self.resize(1280, 800)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self._load_tabs()
        self._create_menu()

    # ============ Carga dinámica de pestañas ============ #
    def _load_tabs(self):
        for mod_name, cls_name, title in _TABS:
            try:
                mod = import_module(f"tabs.{mod_name}")
                cls = getattr(mod, cls_name)
                widget = cls(self.db)
                self.tabs.addTab(widget, title)
            except Exception as e:
                from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
                ph = QWidget()
                lay = QVBoxLayout(ph)
                lay.addWidget(QLabel(f"Error cargando {title}: {e}"))
                self.tabs.addTab(ph, title)

    # =================== Menú =================== #
    def _create_menu(self):
        bar = self.menuBar(); bar.clear()

        m_arch = bar.addMenu("Archivo")
        m_arch.addAction("Nuevo proyecto",  self._new_project)
        m_arch.addAction("Abrir proyecto…", self._open_project)
        m_arch.addAction("Guardar proyecto…", self._save_project)
        m_arch.addSeparator()
        m_arch.addAction("Exportar PDF…", self._export_pdf)

        m_tema = bar.addMenu("Tema")
        m_tema.addAction("Claro",  lambda: self._set_theme("light"))
        m_tema.addAction("Oscuro", lambda: self._set_theme("dark"))

        about = bar.addMenu("Acerca de")
        about.addAction("Sobre la aplicación", self._show_about)

    # ============ Exportar PDF ============ #
    def _export_pdf(self):
        path, _ = QFileDialog.getSaveFileName(self, "Guardar PDF", filter="PDF (*.pdf)")
        if path:
            active = self.tabs.currentWidget()
            if hasattr(active, "export_pdf"):
                active.export_pdf(path)
                QMessageBox.information(self, "Exportar", "PDF generado.")
            else:
                QMessageBox.warning(self, "Exportar", "La pestaña actual no soporta PDF.")

    # ============ Cambiar tema ============ #
    def _set_theme(self, mode):
        qss = Path("themes") / f"{mode}.qss"
        if qss.exists():
            QApplication.instance().setStyleSheet(qss.read_text(encoding="utf-8"))

    # ====================================================================== #
    #  N U E V O   P R O Y E C T O                                           #
    # ====================================================================== #
    def _new_project(self):
        new_db = Database(":memory:")
        self._replace_db_in_tabs(new_db)
        self.unsaved = True
        QMessageBox.information(self, "Nuevo", "Proyecto vacío iniciado.")

    # ====================================================================== #
    #  G U A R D A R   P R O Y E C T O                                        #
    # ====================================================================== #
    def _save_project(self):
        pkg_path, _ = QFileDialog.getSaveFileName(
            self, "Guardar paquete de proyecto", "proyecto.spkg",
            filter="Paquete SeguimientoPro (*.spkg);;ZIP (*.zip)"
        )
        if not pkg_path:
            return

        temp_db = Path(pkg_path).with_suffix(".tmpdb")
        if self.db.db_path == ":memory:":
            try:
                self.db.execute(f"VACUUM main INTO '{temp_db}'")
            except sqlite3.OperationalError:
                with sqlite3.connect(temp_db) as dest:
                    for line in self.db.conn.iterdump():
                        if line not in ("BEGIN;", "COMMIT;"):
                            dest.execute(line)
        else:
            copy2(self.db.db_path, temp_db)

        with ZipFile(pkg_path, "w", ZIP_DEFLATED) as z:
            z.write(temp_db, "atajados.db")
            if IMAGES_DIR.exists():
                for img in IMAGES_DIR.rglob("*"):
                    if img.is_file():
                        z.write(img, Path("images") / img.relative_to(IMAGES_DIR))

        temp_db.unlink(missing_ok=True)
        self.unsaved = False
        QMessageBox.information(self, "Guardar", f"Proyecto guardado en:\n{pkg_path}")

    # ====================================================================== #
    #  A B R I R   P R O Y E C T O                                           #
    # ====================================================================== #
    def _open_project(self):
        pkg, _ = QFileDialog.getOpenFileName(
            self, "Abrir paquete de proyecto",
            filter="Paquete SeguimientoPro (*.spkg *.zip)"
        )
        if not pkg:
            return

        # 1) Descomprimir en carpeta TEMP
        temp_dir = Path(mkdtemp(prefix="seg_loaded_"))
        with ZipFile(pkg, "r") as z:
            z.extractall(temp_dir)

        new_db_path = temp_dir / "atajados.db"
        if not new_db_path.exists():
            QMessageBox.warning(self, "Abrir", "El paquete no contiene atajados.db")
            return

        # 2) Sustituir imágenes
        rmtree(IMAGES_DIR, ignore_errors=True)
        img_src = temp_dir / "images"
        if img_src.exists():
            copytree(img_src, IMAGES_DIR, dirs_exist_ok=True)

        # 3) Crear nueva conexión y sustituir en pestañas
        new_db = Database(new_db_path)
        self._replace_db_in_tabs(new_db)
        self.unsaved = False

        QMessageBox.information(self, "Abrir", "Proyecto cargado correctamente.")

    # ====================================================================== #
    #  H E L P E R S                                                          #
    # ====================================================================== #
    def _replace_db_in_tabs(self, new_db: Database):
        """Sustituye la conexión en todas las pestañas y refresca."""
        old_db = self.db
        self.db = new_db
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if hasattr(w, "db"):
                w.db = new_db
            for m in ("refresh", "load_items"):
                if hasattr(w, m):
                    getattr(w, m)()
        if old_db:
            old_db.close()

    # ---------------- Acerca de ---------------- #
    def _show_about(self):
        QMessageBox.about(
            self,
            "Acerca de Seguimiento de Atajados",
            "<h3>Seguimiento de Atajados – Totora</h3>"
            "<p>Versión modular PyQt6.</p>"
            "<p>Desarrollador: <b>WILO</b></p>",
        )
