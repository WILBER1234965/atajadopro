
from project_manager import ProyectoManager
from ui.main_window import MainWindow

class SeguimientoProApp:
    """Shell ligero que contiene la ventana principal y expone run()"""

    def __init__(self, qt_app):
        self.qt_app = qt_app
        self.manager = ProyectoManager()
        self.window = MainWindow(self.manager)

    def run(self) -> int:
        self.window.show()
        return self.qt_app.exec()
