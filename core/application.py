"""Orquestador principal de SeguimientoPro."""

from pathlib import Path
from tempfile import mkdtemp
from shutil import rmtree

from database import Database, IMAGES_DIR
from app import SeguimientoProApp


class Application:
    """
    • Arranca con una BD en memoria (proyecto sin título).
    • Mantiene un flag `unsaved` para saber si existe archivo físico.
    • Permite que MainWindow le pida refrescar todas las pestañas.
    """

    def __init__(self, qt_app):
        # Proyecto “sin título” en memoria
        self.db = Database(":memory:")
        self.unsaved = True       # ← banderín: nada guardado aún

        # Carpeta temporal de imágenes de trabajo
        self.temp_dir = Path(mkdtemp(prefix="seg_temp_"))
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)

        # Ventana principal
        self.app_shell = SeguimientoProApp(qt_app, self.db)
        # Inyectar callback para refrescar desde MainWindow
        self.app_shell.window.refresh_all = self.refresh_all_tabs

        self.set_theme("light")

    # ---------------- API pública ---------------- #
    def run(self) -> int:
        exit_code = self.app_shell.run()
        self.db.close()
        # Limpia carpeta temp si sigue existiendo
        try:
            rmtree(self.temp_dir)
        except Exception:
            pass
        return exit_code

    # ---------------- Helpers -------------------- #
    def set_theme(self, mode: str) -> None:
        from PyQt6.QtWidgets import QApplication

        qss = Path("themes") / f"{mode}.qss"
        if qss.exists():
            QApplication.instance().setStyleSheet(
                qss.read_text(encoding="utf-8", errors="ignore")
            )

    # ---------------- Refresco global ------------ #
    def refresh_all_tabs(self):
        """Recorre todas las pestañas y llama a refresh/load_items si existen."""
        wnd = self.app_shell.window
        for i in range(wnd.tabs.count()):
            w = wnd.tabs.widget(i)
            for m in ("refresh", "load_items"):
                if hasattr(w, m):
                    getattr(w, m)()
