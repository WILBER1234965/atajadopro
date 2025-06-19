# cronograma_tab.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QSplitter, QTableWidget, QTableWidgetItem
)
from PyQt6.QtCore import Qt
from matplotlib.backends.backend_qtagg import (
    FigureCanvasQTAgg as FigureCanvas,
    NavigationToolbar2QT as NavigationToolbar,
)
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import datetime

class CronogramaTab(QWidget):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.tasks = []
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Control de escala
        ctrl = QHBoxLayout()
        lbl = QLabel("% escala:")
        self.cmb_scale = QComboBox()
        self.cmb_scale.addItems(["100", "80", "60", "40", "20"])
        self.cmb_scale.setCurrentText("80")
        self.cmb_scale.currentTextChanged.connect(self.draw_gantt)
        ctrl.addWidget(lbl)
        ctrl.addWidget(self.cmb_scale)
        ctrl.addStretch()
        layout.addLayout(ctrl)

        # Splitter: tabla y gráfico Gantt
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Tabla de items
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Nº", "Actividad", "Hrs.", "Inicia", "Finaliza", "C.", "P.", "Días"
        ])
        self.table.setAlternatingRowColors(True)
        splitter.addWidget(self.table)

        # Contenedor de gráfico
        gantt_widget = QWidget()
        gantt_layout = QVBoxLayout(gantt_widget)
        self.figure = plt.Figure()
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, self)
        gantt_layout.addWidget(self.toolbar)
        gantt_layout.addWidget(self.canvas)
        splitter.addWidget(gantt_widget)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter)

        # Carga data y pinta
        self.load_data()

    def load_data(self):
        """
        Carga ítems y fechas desde tabla 'avances'.
        """
        sql = (
            "SELECT i.id, i.name, "
            "MIN(a.date) AS start_date, MAX(a.date) AS end_date "
            "FROM items i "
            "JOIN avances a ON a.item_id = i.id "
            "GROUP BY i.id, i.name "
            "ORDER BY i.id;"
        )
        rows = self.db.fetchall(sql)
        self.tasks = []
        for item_id, name, start_val, end_val in rows:
            # Ignorar registros sin fechas
            if start_val is None or end_val is None:
                continue
            # Convertir tipos
            if isinstance(start_val, str):
                start = datetime.datetime.strptime(start_val, "%Y-%m-%d").date()
            else:
                start = start_val
            if isinstance(end_val, str):
                end = datetime.datetime.strptime(end_val, "%Y-%m-%d").date()
            else:
                end = end_val
            days = (end - start).days
            hours = days * 8  # Estimación: 8h por día
            self.tasks.append({
                "id": item_id,
                "activity": name,
                "hours": hours,
                "start": start,
                "end": end,
                "c": 0,
                "p": 0,
                "days": days
            })
        # Rellena la tabla
        self.table.setRowCount(len(self.tasks))
        for i, t in enumerate(self.tasks):
            self.table.setItem(i, 0, QTableWidgetItem(str(t["id"])))
            self.table.setItem(i, 1, QTableWidgetItem(t["activity"]))
            self.table.setItem(i, 2, QTableWidgetItem(str(t["hours"])))
            self.table.setItem(i, 3, QTableWidgetItem(t["start"].strftime("%d/%m/%y")))
            self.table.setItem(i, 4, QTableWidgetItem(t["end"].strftime("%d/%m/%y")))
            self.table.setItem(i, 5, QTableWidgetItem(str(t["c"])))
            self.table.setItem(i, 6, QTableWidgetItem(str(t["p"])))
            self.table.setItem(i, 7, QTableWidgetItem(str(t["days"])))
        # Pinta el Gantt
        self.draw_gantt()

    def draw_gantt(self):
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        if not self.tasks:
            self.canvas.draw()
            return

        # Configurar límites de fecha
        starts = [t["start"] for t in self.tasks]
        ends = [t["end"] for t in self.tasks]
        min_date = min(starts) - datetime.timedelta(days=1)
        max_date = max(ends) + datetime.timedelta(days=1)
        ax.set_xlim(mdates.date2num(min_date), mdates.date2num(max_date))

        # Formato eje X: meses y semanas
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b/%Y'))
        ax.xaxis.set_minor_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
        ax.grid(True, which='minor', axis='x', linestyle='--', color='red')
        ax.grid(True, which='major', axis='x', linestyle='-', color='black', linewidth=1)

        # Dibujar barras y etiquetas
        yticks, ylabels = [], []
        for idx, t in enumerate(self.tasks):
            start_num = mdates.date2num(t["start"])
            duration = t["days"]
            ax.broken_barh([(start_num, duration)], (idx*10, 9), facecolors='tab:red')
            yticks.append(idx*10 + 4.5)
            ylabels.append(f"{t['id']}. {t['activity']}")
            ax.text(start_num + duration/2, idx*10 + 4.5,
                    f"{duration} d.", ha='center', va='center', fontsize=8)

        ax.set_yticks(yticks)
        ax.set_yticklabels(ylabels)
        ax.set_ylabel('Actividades')
        ax.set_xlabel('Fecha')

        # Línea de hoy
        hoy = datetime.date.today()
        ax.axvline(mdates.date2num(hoy), color='blue', linestyle='--')

        self.figure.autofmt_xdate(rotation=30)
        self.canvas.draw()

    def refresh(self):
        """Recargar datos y redibujar el cronograma."""
        self.load_data()