from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt
import pyqtgraph as pg
from database import Database

class DashboardTab(QWidget):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db

        # Layout principal --------------------------------------------------
        main_layout = QVBoxLayout(self)
        title = QLabel("<h1>Dashboard de Supervisión</h1>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title)

        # --------- Métricas -------------------------------------------------
        metrics_layout = QHBoxLayout()
        metrics = [
            ("Total Atajados", "icons/total.png",       lambda: self.get_count()),
            ("Ejecutados",     "icons/executed.png",    lambda: self.get_count("Ejecutado")),
            ("En ejecución",   "icons/running.png",     lambda: self.get_count("En ejecución")),
            ("Pendientes",     "icons/pending.png",     lambda: self.get_pending()),
        ]
        self.metric_labels = []
        for text, icon_path, fn in metrics:
            w = QWidget(); v = QVBoxLayout(w)

            icon_lbl = QLabel()
            icon_lbl.setPixmap(QPixmap(icon_path).scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio,
                                                         Qt.TransformationMode.SmoothTransformation))
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

            value_lbl = QLabel(f"<b>{fn()}</b>")
            value_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

            caption = QLabel(text)
            caption.setAlignment(Qt.AlignmentFlag.AlignCenter)

            v.addWidget(icon_lbl); v.addWidget(value_lbl); v.addWidget(caption)
            metrics_layout.addWidget(w)
            self.metric_labels.append((value_lbl, fn))
        main_layout.addLayout(metrics_layout)

        # --------- Avance global -------------------------------------------
        self.progress_label = QLabel(f"Avance del Proyecto: {self.db.get_project_progress():.0f}%")
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.progress_label)

        # --------- Gráfica --------------------------------------------------
        self.chart = pg.PlotWidget()
        counts = [self.get_count(),
                  self.get_count("Ejecutado"),
                  self.get_count("En ejecución"),
                  self.get_pending()]
        self.bar = pg.BarGraphItem(x=[0,1,2,3], height=counts, width=0.6, brush="skyblue")
        self.chart.addItem(self.bar)
        self.chart.getAxis("bottom").setTicks([[(0,"Total"),(1,"Ejecutado"),(2,"En ejec."),(3,"Pendiente")]])
        main_layout.addWidget(self.chart); main_layout.addStretch()

        # Tema inicial (claro por defecto)
        self.set_theme(dark=False)

    # ------------------------ Tema -----------------------------------------
    def set_theme(self, dark: bool):
        """Ajusta colores de la gráfica según el tema."""
        bg   = "#1e1e1e" if dark else "#ffffff"
        axis = "#dddddd" if dark else "#202020"
        bars = "skyblue" if not dark else "#5dade2"

        self.chart.setBackground(bg)
        ax = self.chart.getAxis("left");  ax.setPen(axis)
        ax = self.chart.getAxis("bottom"); ax.setPen(axis)
        self.bar.setOpts(brush=bars, pen=axis)

    # ------------------------ Refresh --------------------------------------
    def refresh(self):
        for lbl, fn in self.metric_labels:
            lbl.setText(f"<b>{fn()}</b>")
        counts = [self.get_count(), self.get_count("Ejecutado"),
                  self.get_count("En ejecución"), self.get_pending()]
        self.bar.setOpts(height=counts)
        self.progress_label.setText(f"Avance del Proyecto: {self.db.get_project_progress():.0f}%")

    # ------------------------ Queries --------------------------------------
    def get_count(self, status=None) -> int:
        if status:
            return self.db.fetchall("SELECT COUNT(*) FROM atajados WHERE status=?", (status,))[0][0]
        return self.db.fetchall("SELECT COUNT(*) FROM atajados")[0][0]

    def get_pending(self) -> int:
        return (self.get_count() -
                self.get_count("Ejecutado") -
                self.get_count("En ejecución"))
