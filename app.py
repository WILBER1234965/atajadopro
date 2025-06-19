
from ui.main_window import MainWindow

class SeguimientoProApp:
    """Shell ligero que contiene la ventana principal y expone run()"""

    def __init__(self, qt_app, db):
        self.qt_app = qt_app
        self.window = MainWindow(db)

    def run(self) -> int:
        self.window.show()
        return self.qt_app.exec()
