# ui/main_window.py
from pathlib import Path
from importlib import import_module


from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui  import QIcon, QAction, QColor, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QFileDialog, QMessageBox,
    QLabel, QDialog, QVBoxLayout, QHBoxLayout, QPushButton
)

from project_manager import ProyectoManager

# ----------------------------- Lista de pestañas ------------------------------
_TABS = [
    ("dashboard_tab",  "DashboardTab",   "Dashboard"),
    ("items_tab",      "ItemsTab",       "Ítems"),
    ("atajados_tab",   "AtajadosTab",    "Atajados"),
    ("avance_tab",     "AvanceTab",      "Avance"),
    ("cronograma_tab", "CronogramaTab",  "Cronograma"),
    ("summary_tab",    "SummaryTab",     "Resumen"),
]


class MainWindow(QMainWindow):
    """Ventana principal con QTabWidget oculto y navegación vía menú."""

    # -------------------------------------------------------------------------
    def __init__(self, manager: ProyectoManager):
        super().__init__()
        self.manager = manager
        self.db = manager.proyecto.db
        self.setWindowTitle("Seguimiento de Atajados")
        self.resize(1280, 800)

        self._init_tabs()        # contenedor de vistas
        self._init_menu()        # barra de menú con navegación
        self._init_statusbar()   # “Estás en: …”
        self._apply_theme("dark")
        self.manager.dirtyChanged.connect(self._update_title)
        self.manager.pathChanged.connect(self._update_title)
        self._update_title()
    # -------------------------------------------------------------------------
    # Tabs (contenedor de vistas)
    # -------------------------------------------------------------------------
    def _init_tabs(self):
        self.tabs = QTabWidget()
        self.tabs.tabBar().setVisible(False)           # ocultar pestañas
        self.setCentralWidget(self.tabs)

        self._title_to_index = {}                      # mapa: título → índice

        for module_name, class_name, title in _TABS:
            try:
                module  = import_module(f"tabs.{module_name}")
                cls     = getattr(module, class_name)
                widget  = cls(self.db)
            except Exception as e:
                widget  = QLabel(f"Error cargando {title}: {e}")

            idx = self.tabs.addTab(widget, title)
            self._title_to_index[title] = idx

        self.tabs.currentChanged.connect(self._update_status)

    # -------------------------------------------------------------------------
    # Barra de menú
    # -------------------------------------------------------------------------
    def _init_menu(self):
        mb = self.menuBar()
        mb.clear()

        # Archivo
        m_arch = mb.addMenu("Archivo")
        m_arch.addAction("Nuevo proyecto",  self._new_project)
        m_arch.addAction("Abrir proyecto…", self._open_project)
        m_arch.addAction("Guardar proyecto…", self._save_project)
        m_arch.addSeparator()
        m_arch.addAction("Exportar PDF…", self._export_pdf)



        # Inicio
        m_ini = mb.addMenu("Inicio")
        m_ini.addAction("Dashboard", lambda: self._goto("Dashboard"))

        # Datos
        m_datos = mb.addMenu("Datos")
        m_datos.addAction("Ítems",    lambda: self._goto("Ítems"))
        m_datos.addAction("Atajados", lambda: self._goto("Atajados"))

        # Seguimiento
        m_seg = mb.addMenu("Seguimiento")
        m_seg.addAction("Avance",     lambda: self._goto("Avance"))

        # Resultados
        m_res = mb.addMenu("Resultados")
        m_res.addAction("Cronograma", lambda: self._goto("Cronograma"))
        m_res.addAction("Resumen",    lambda: self._goto("Resumen"))

        # Configuración
        m_conf = mb.addMenu("Configuración")
        m_conf.addAction("Tema Claro",  lambda: self._apply_theme("light"))
        m_conf.addAction("Tema Oscuro", lambda: self._apply_theme("dark"))

        # Acerca de
        m_about = mb.addMenu("Acerca de")
        m_about.addAction("Sobre la aplicación", self._show_about)

    # -------------------------------------------------------------------------
    # Barra de estado
    # -------------------------------------------------------------------------
    def _init_statusbar(self):
        self.status_label = QLabel()
        self.statusBar().addPermanentWidget(self.status_label)
        self._update_status()

    def _update_title(self):
        name = self.manager.proyecto.path.name if self.manager.proyecto.path else "Sin título"
        title = f"Seguimiento de Atajados - {name}"
        if self.manager.is_dirty:
            title = "*" + title
        self.setWindowTitle(title)

    def _update_status(self, *_):
        self.status_label.setText(f"Estás en: {self.tabs.tabText(self.tabs.currentIndex())}")

    # -------------------------------------------------------------------------
    # Navegación helper
    # -------------------------------------------------------------------------
    def _goto(self, title: str):
        if title in self._title_to_index:
            self.tabs.setCurrentIndex(self._title_to_index[title])

    # -------------------------------------------------------------------------
    # Tema
    # -------------------------------------------------------------------------
    def _apply_theme(self, mode: str):
        qss = Path("themes") / f"{mode}.qss"
        if qss.exists():
            QApplication.instance().setStyleSheet(qss.read_text(encoding="utf-8"))
        QSettings("WILO", "SeguimientoPro").setValue("theme", mode)

    # -------------------------------------------------------------------------
    # Exportar PDF
    # -------------------------------------------------------------------------
    def _export_pdf(self):
        path, _ = QFileDialog.getSaveFileName(self, "Guardar PDF", filter="PDF (*.pdf)")
        if not path:
            return
        current = self.tabs.currentWidget()
        if hasattr(current, "export_pdf"):
            current.export_pdf(path)
            QMessageBox.information(self, "Exportar", "PDF generado correctamente.")
        else:
            QMessageBox.warning(self, "Exportar", "La vista actual no soporta PDF.")

    # -------------------------------------------------------------------------
    # Nuevo / Abrir / Guardar
    # -------------------------------------------------------------------------
    def _new_project(self):
        self.manager.new_project()
        self._replace_db(self.manager.proyecto.db)
        QMessageBox.information(self, "Nuevo", "Proyecto vacío iniciado.")

    def _save_project(self):
         if self.manager.proyecto.path is None:
            path, _ = QFileDialog.getSaveFileName(
                self, "Guardar", filter="Paquete SeguimientoPro (*.spkg)"
            )
            if not path:
                return
            self.manager.save_project(path)

         else:
            self.manager.save_project()
    
            QMessageBox.information(self, "Guardar", "Proyecto guardado.")

    def _open_project(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Abrir", filter="Paquete SeguimientoPro (*.spkg *.zip)"
        )
        if not path:
            return
        try:
            self.manager.open_project(path)
        except Exception as e:
            QMessageBox.warning(self, "Abrir", str(e))

            return
        self._replace_db(self.manager.proyecto.db)
        QMessageBox.information(self, "Abrir", "Proyecto cargado correctamente.")

    def _replace_db(self, new_db: Database):
        self.db = new_db
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if hasattr(w, "db"):
                w.db = new_db
            for m in ("refresh", "load_items"):
                if hasattr(w, m):
                    getattr(w, m)()
        self._update_title()
    # -------------------------------------------------------------------------
    # Diálogo Acerca de
    # -------------------------------------------------------------------------
    def _show_about(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Acerca de – Seguimiento de Atajados")
        dlg.setFixedSize(400, 350)
        dlg.setStyleSheet("""
            QDialog { background-color: #f5f5f5; }
            QLabel#title { color: #2c3e50; font-size: 18pt; font-weight: bold; }
            QLabel#body  { color: #34495e; font-size: 10pt; }
            QPushButton {
                background: #1976D2; color: white; border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:hover { background: #1259a4; }
        """)
        lay = QVBoxLayout(dlg)

        logo = QLabel()
        pix  = QPixmap("images/logo.png").scaled(
            100, 100, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        logo.setPixmap(pix)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(logo)

        title = QLabel("Seguimiento de Atajados", objectName="title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)

        body  = QLabel(
            "Versión modular <b>PyQt6</b><br>"
            "Desarrollador: <b>WILO</b><br><br>"
            "© 2025 WILO. Todos los derechos reservados.",
            objectName="body"
        )
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.setWordWrap(True)
        lay.addWidget(body)

        btn = QPushButton("Cerrar", clicked=dlg.accept)
        hl = QHBoxLayout()
        hl.addStretch()
        hl.addWidget(btn)
        hl.addStretch()
        lay.addLayout(hl)

        dlg.exec()


# --------------------------- Launcher directo ---------------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    manager = ProyectoManager()
    win = MainWindow(manager)
    win.show()
    sys.exit(app.exec())
