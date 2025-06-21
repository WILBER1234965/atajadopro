from __future__ import annotations

import sys
from pathlib import Path
from importlib import import_module

from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import (
    QIcon,
    QAction,
    QColor,
    QPixmap,
    QCloseEvent,  # interceptar cierre de ventana
)
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QTabWidget,
    QFileDialog,
    QMessageBox,
    QLabel,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
)

from database import Database
from project_manager import ProyectoManager

# ----------------------------- Lista de pestañas ------------------------------
_TABS = [
    ("dashboard_tab",  "DashboardTab",  "Dashboard"),
    ("items_tab",      "ItemsTab",      "Ítems"),
    ("atajados_tab",   "AtajadosTab",   "Atajados"),
    ("avance_tab",     "AvanceTab",     "Avance"),
    ("cronograma_tab", "CronogramaTab", "Cronograma"),
    ("summary_tab",    "SummaryTab",    "Resumen"),
]


class MainWindow(QMainWindow):
    """Ventana principal con QTabWidget oculto y navegación vía menú."""

    # --------------------------------------------------------------------- #
    def __init__(self, manager: ProyectoManager):
        super().__init__()
        self.manager = manager
        self.db: Database = manager.proyecto.db

        self.setWindowTitle("Seguimiento de Atajados")
        self.resize(1280, 800)

        self._init_tabs()        # contenedor de vistas
        self._init_menu()        # barra de menú
        self._init_statusbar()   # barra de estado
        self._apply_theme("dark")

        # señales → título
        self.manager.dirtyChanged.connect(self._update_title)
        self.manager.pathChanged.connect(self._update_title)
        self._update_title()

    # --------------------------------------------------------------------- #
    # Tabs (contenedor de vistas)
    # --------------------------------------------------------------------- #
    def _init_tabs(self):
        self.tabs = QTabWidget()
        self.tabs.tabBar().setVisible(False)       # ocultar pestañas
        self.setCentralWidget(self.tabs)

        self._title_to_index: dict[str, int] = {}

        for module_name, class_name, title in _TABS:
            try:
                module  = import_module(f"tabs.{module_name}")
                cls     = getattr(module, class_name)
                widget  = cls(self.db)
            except Exception as exc:               # pragma: no cover
                widget  = QLabel(f"Error cargando {title}: {exc}")
            idx = self.tabs.addTab(widget, title)
            self._title_to_index[title] = idx

        self.tabs.currentChanged.connect(self._update_status)

    # --------------------------------------------------------------------- #
    # Barra de menú
    # --------------------------------------------------------------------- #
    def _init_menu(self):
        mb = self.menuBar()
        mb.clear()

        # ─────────────── Archivo ───────────────
        m_arch = mb.addMenu("Archivo")
        m_arch.addAction("Nuevo proyecto",  self._new_project)
        m_arch.addAction("Abrir proyecto…", self._open_project)

        act_save = QAction("Guardar", self)
        act_save.setShortcut("Ctrl+S")
        act_save.triggered.connect(self._save_project)
        m_arch.addAction(act_save)

        act_save_as = QAction("Guardar como…", self)
        act_save_as.setShortcut("Ctrl+Shift+S")
        act_save_as.triggered.connect(self._save_project_as)
        m_arch.addAction(act_save_as)

        m_arch.addSeparator()
        m_arch.addAction("Exportar PDF…", self._export_pdf)

        # ─────────────── Inicio ───────────────
        m_ini = mb.addMenu("Inicio")
        m_ini.addAction("Dashboard", lambda: self._goto("Dashboard"))

        # ─────────────── Datos ────────────────
        m_datos = mb.addMenu("Datos")
        m_datos.addAction("Ítems",    lambda: self._goto("Ítems"))
        m_datos.addAction("Atajados", lambda: self._goto("Atajados"))

        # ───────────── Seguimiento ────────────
        m_seg = mb.addMenu("Seguimiento")
        m_seg.addAction("Avance",     lambda: self._goto("Avance"))

        # ───────────── Resultados ─────────────
        m_res = mb.addMenu("Resultados")
        m_res.addAction("Cronograma", lambda: self._goto("Cronograma"))
        m_res.addAction("Resumen",    lambda: self._goto("Resumen"))

        # ──────────── Configuración ───────────
        m_conf = mb.addMenu("Configuración")
        m_conf.addAction("Tema Claro",  lambda: self._apply_theme("light"))
        m_conf.addAction("Tema Oscuro", lambda: self._apply_theme("dark"))

        # ────────────── Acerca de ─────────────
        m_about = mb.addMenu("Acerca de")
        m_about.addAction("Sobre la aplicación", self._show_about)

    # --------------------------------------------------------------------- #
    # Barra de estado
    # --------------------------------------------------------------------- #
    def _init_statusbar(self):
        self.status_label = QLabel()
        self.statusBar().addPermanentWidget(self.status_label)
        self._update_status()

    def _update_title(self):
        name = self.manager.proyecto.path.name if self.manager.proyecto.path else "Sin título"
        title = f"Seguimiento de Atajados – {name}"
        if self.manager.is_dirty:
            title = "*" + title
        self.setWindowTitle(title)

    def _update_status(self, *_):
        self.status_label.setText(f"Estás en: {self.tabs.tabText(self.tabs.currentIndex())}")

    # --------------------------------------------------------------------- #
    # Navegación helper
    # --------------------------------------------------------------------- #
    def _goto(self, title: str):
        """Cambiar a la pestaña *title* si existe."""
        if title in self._title_to_index:
            self.tabs.setCurrentIndex(self._title_to_index[title])

    # --------------------------------------------------------------------- #
    # Tema
    # --------------------------------------------------------------------- #
    def _apply_theme(self, mode: str):
        qss = Path("themes") / f"{mode}.qss"
        if qss.exists():
            QApplication.instance().setStyleSheet(qss.read_text(encoding="utf-8"))
        QSettings("WILO", "SeguimientoPro").setValue("theme", mode)

    # --------------------------------------------------------------------- #
    # Exportar PDF de la vista activa
    # --------------------------------------------------------------------- #
    def _export_pdf(self):
        path, _ = QFileDialog.getSaveFileName(self, "Guardar PDF", filter="PDF (*.pdf)")
        if not path:
            return
        current = self.tabs.currentWidget()
        if hasattr(current, "export_pdf"):
            current.export_pdf(path)
            QMessageBox.information(self, "Exportar", "PDF generado correctamente.")
        else:
            QMessageBox.warning(self, "Exportar", "La vista actual no soporta exportar a PDF.")

    # --------------------------------------------------------------------- #
    # Helpers de guardado y protección de cambios
    # --------------------------------------------------------------------- #
    def _maybe_save(self) -> bool:
        """Preguntar si hay cambios sin guardar.
        • True  → se puede continuar
        • False → operación cancelada
        """
        if not self.manager.is_dirty:
            return True

        resp = QMessageBox.question(
            self,
            "Cambios sin guardar",
            "¿Desea guardar los cambios antes de continuar?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,
        )
        if resp == QMessageBox.StandardButton.Cancel:
            return False
        if resp == QMessageBox.StandardButton.No:
            return True
        # Elegido “Sí” → intentar guardar
        return self._save_project(show_messages=False)

    # --------------------------------------------------------------------- #
    # Nuevo / Abrir
    # --------------------------------------------------------------------- #
    def _new_project(self):
        if not self._maybe_save():
            return
        self.manager.new_project()
        self._replace_db(self.manager.proyecto.db)
        QMessageBox.information(self, "Nuevo", "Proyecto vacío iniciado.")

    def _open_project(self):
        if not self._maybe_save():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Abrir", filter="Paquete SeguimientoPro (*.spkg *.zip)"
        )
        if not path:
            return
        try:
            self.manager.open_project(path)
        except Exception as exc:
            QMessageBox.warning(self, "Abrir", str(exc))
            return
        self._replace_db(self.manager.proyecto.db)
        QMessageBox.information(self, "Abrir", "Proyecto cargado correctamente.")

    # --------------------------------------------------------------------- #
    # Guardar / Guardar como
    # --------------------------------------------------------------------- #
    def _save_project(self, *, show_messages: bool = True) -> bool:
        """Guardar (Ctrl+S). Devuelve True si se guardó con éxito."""
        # Si no hay ruta todavía → actuar como Guardar como…
        if self.manager.proyecto.path is None:
            return self._save_project_as(show_messages=show_messages)

        ok = self.manager.save_project()
        if ok and show_messages:
            QMessageBox.information(self, "Guardar", "Proyecto guardado.")
        return ok

    def _save_project_as(self, *, show_messages: bool = True) -> bool:
        """Guardar como… (Ctrl+Shift+S)."""
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar como",
            filter="Paquete SeguimientoPro (*.spkg)",
        )
        if not path:
            return False

        ok = self.manager.save_project(Path(path))
        if ok and show_messages:
            QMessageBox.information(self, "Guardar como", "Proyecto guardado.")
        return ok

    # --------------------------------------------------------------------- #
    # Propagar nueva conexión DB a las pestañas
    # --------------------------------------------------------------------- #
    def _replace_db(self, new_db: Database):
        self.db = new_db
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            if hasattr(widget, "db"):
                widget.db = new_db
            for method in ("refresh", "load_items"):
                if hasattr(widget, method):
                    getattr(widget, method)()
        self._update_title()

    # --------------------------------------------------------------------- #
    # Diálogo “Acerca de…”
    # --------------------------------------------------------------------- #
    def _show_about(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Acerca de – Seguimiento de Atajados")
        dlg.setFixedSize(400, 350)
        dlg.setStyleSheet(
            """
            QDialog { background-color: #f5f5f5; }
            QLabel#title { color: #2c3e50; font-size: 18pt; font-weight: bold; }
            QLabel#body  { color: #34495e; font-size: 10pt; }
            QPushButton {
                background: #1976D2; color: white; border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:hover { background: #1259a4; }
            """
        )
        lay = QVBoxLayout(dlg)

        logo = QLabel()
        pix = QPixmap("images/logo.png").scaled(
            100, 100,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        logo.setPixmap(pix)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(logo)

        title_lbl = QLabel("Seguimiento de Atajados", objectName="title")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title_lbl)

        body_lbl = QLabel(
            "Versión modular <b>PyQt6</b><br>"
            "Desarrollador: <b>WILO</b><br><br>"
            "© 2025 WILO. Todos los derechos reservados.",
            objectName="body",
        )
        body_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body_lbl.setWordWrap(True)
        lay.addWidget(body_lbl)

        btn = QPushButton("Cerrar", clicked=dlg.accept)
        hbtn = QHBoxLayout()
        hbtn.addStretch()
        hbtn.addWidget(btn)
        hbtn.addStretch()
        lay.addLayout(hbtn)

        dlg.exec()

    # --------------------------------------------------------------------- #
    # Cerrar la ventana principal → ¿guardar antes?
    # --------------------------------------------------------------------- #
    def closeEvent(self, event: QCloseEvent):  # noqa: N802 (Qt naming)
        if self._maybe_save():
            event.accept()
            self.manager.close()
        else:
            event.ignore()


# --------------------------- EJECUCIÓN DIRECTA ------------------------------- #
if __name__ == "__main__":
    app = QApplication(sys.argv)
    manager = ProyectoManager()
    win = MainWindow(manager)
    win.show()
    sys.exit(app.exec())
