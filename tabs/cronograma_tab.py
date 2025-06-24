from __future__ import annotations

import pandas as pd
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.ticker import FuncFormatter

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel,
    QScrollArea, QFrame
)
from PyQt6.QtCore import Qt

from database import Database


class CronogramaTab(QWidget):
    """Muestra un diagrama de Gantt basado en los avances."""

    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Scroll horizontal
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)

        # Contenedor interno con layout vertical
        self.container = QFrame()
        self.container_layout = QVBoxLayout(self.container)

        # Canvas de días de semana (superior)
        self.days_canvas = FigureCanvasQTAgg(plt.Figure(figsize=(20, 1)))
        self.days_ax = self.days_canvas.figure.subplots()
        self.container_layout.addWidget(self.days_canvas)

        # Canvas principal de Gantt
        self.canvas = FigureCanvasQTAgg(plt.Figure(figsize=(20, 6)))
        self.ax = self.canvas.figure.subplots()
        self.ax_top = self.ax.twiny()
        self.container_layout.addWidget(self.canvas)

        # Definir tamaño mínimo amplio para permitir scroll horizontal
        self.container.setMinimumWidth(1800)
        self.scroll_area.setWidget(self.container)
        layout.addWidget(self.scroll_area)

        # Botón de actualizar
        self.refresh_btn = QPushButton("Refrescar")
        self.refresh_btn.clicked.connect(self.refresh)
        layout.addWidget(self.refresh_btn)

        self.no_data_lbl = QLabel("Sin datos")
        self.no_data_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.no_data_lbl.hide()
        layout.addWidget(self.no_data_lbl)

    def refresh(self) -> None:
        rows = self.db.fetchall(
            """
            SELECT i.name, a.start_date, a.end_date
            FROM items i
            JOIN avances a ON a.item_id = i.id
            WHERE a.start_date IS NOT NULL AND a.end_date IS NOT NULL
            ORDER BY i.id, a.start_date
            """
        )

        df = pd.DataFrame(rows, columns=["name", "start", "end"])
        df["start"] = pd.to_datetime(df["start"])
        df["end"] = pd.to_datetime(df["end"])

        self.ax.clear()
        self.ax_top.clear()
        self.days_ax.clear()

        if df.empty:
            self.no_data_lbl.show()
            self.canvas.draw()
            return

        self.no_data_lbl.hide()

        # Agrupar datos
        groups = {}
        days = {}
        for name, g in df.groupby("name"):
            segs = []
            total = 0
            for s, e in zip(g["start"], g["end"]):
                start_num = mdates.date2num(s)
                width = (e - s).days or 1
                segs.append((start_num, width))
                total += width
            groups[name] = segs
            days[name] = total

        ylabels = list(groups.keys())
        cmap = plt.get_cmap("tab20")
        for idx, name in enumerate(ylabels):
            color = cmap(idx % cmap.N)
            self.ax.broken_barh(groups[name], (idx - 0.4, 0.8), facecolors=color)
            end_pos = max(x + w for x, w in groups[name])
            self.ax.text(end_pos + 0.5, idx, f"{days[name]}d", va="center", fontsize=8)

        self.ax.set_xlabel("Fecha")
        self.ax.set_yticks(range(len(ylabels)))
        self.ax.set_yticklabels(ylabels)
        self.ax.invert_yaxis()

        start = df["start"].min()
        end = df["end"].max()
        self.ax.set_xlim(mdates.date2num(start) - 1, mdates.date2num(end) + 1)

        # Formato inferior con letras de día
        dias = ["L", "M", "X", "J", "V", "S", "D"]
        self.ax.xaxis.set_major_locator(mdates.DayLocator())
        self.ax.xaxis.set_major_formatter(
            FuncFormatter(lambda d, _: dias[mdates.num2date(d).weekday()])
        )

        # Encabezado superior: meses
        self.ax_top.set_xlim(self.ax.get_xlim())
        self.ax_top.xaxis.set_major_locator(mdates.MonthLocator())
        self.ax_top.xaxis.set_major_formatter(mdates.DateFormatter("%b-%y"))
        self.ax_top.xaxis.set_ticks_position("top")
        self.ax_top.spines["bottom"].set_visible(False)

        # ─────── Cuadros superiores de días de la semana ─────── #
        self.days_ax.set_xlim(self.ax.get_xlim())
        self.days_ax.set_ylim(0, 1)
        self.days_ax.axis("off")

        dia_actual = pd.Timestamp(start)
        while dia_actual <= end:
            dnum = mdates.date2num(dia_actual)
            nombre = dias[dia_actual.weekday()]
            self.days_ax.add_patch(
                plt.Rectangle((dnum - 0.5, 0), 1, 1, facecolor="white", edgecolor="black")
            )
            self.days_ax.text(dnum, 0.5, nombre, va="center", ha="center", fontsize=8)
            dia_actual += pd.Timedelta(days=1)

        # Cuadrícula
        self.ax.grid(axis="y", color="#cccccc", linestyle="-", linewidth=0.5)
        weeks = mdates.WeekdayLocator(byweekday=0)
        self.ax.vlines(
            weeks.tick_values(start, end),
            -1,
            len(ylabels),
            colors="#cccccc",
            linewidth=0.5,
        )

        # Dibujar
        self.days_canvas.figure.tight_layout()
        self.days_canvas.draw()
        self.canvas.figure.tight_layout()
        self.canvas.draw()
