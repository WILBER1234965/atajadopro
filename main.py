
import sys
from PyQt6.QtWidgets import QApplication
from core.application import Application

def main():
    qt_app = QApplication(sys.argv)
    app = Application(qt_app)
    sys.exit(app.run())

if __name__ == '__main__':
    main()
