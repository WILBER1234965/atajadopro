
import sys
from PyQt6.QtWidgets import QApplication
from app import SeguimientoProApp

def main():
    qt_app = QApplication(sys.argv)
    app = SeguimientoProApp(qt_app)
    sys.exit(app.run())

if __name__ == '__main__':
    main()
