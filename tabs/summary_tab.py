# summary_tab.py
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem
from PyQt6.QtCore import Qt
from database import Database

class SummaryTab(QWidget):
    """Display progress summary per atajado."""
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        layout = QVBoxLayout(self)
        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        self.refresh()

    def refresh(self):
        at_rows = self.db.fetchall("SELECT number, beneficiario FROM atajados")
        rows = []
        for num, ben in at_rows:
            dt = self.db.fetchall(
                "SELECT MAX(date) FROM avances WHERE atajado_id=?",
                (num,)
            )[0][0]
            pct_row = self.db.fetchall(
                """
                SELECT SUM(i.total*i.incidence*a.quantity/100.0) / SUM(i.total*i.incidence)
                FROM avances a JOIN items i ON a.item_id=i.id
                WHERE a.atajado_id=? AND i.active=1
                """,
                (num,)
            )
            pct = (pct_row[0][0] or 0) * 100
            rows.append((num, ben, dt if dt else "", pct))
        rows.sort(key=lambda x: x[2], reverse=True)

        headers = ["Atajado", "Beneficiario", "Fecha", "Avance (%)"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(rows))
        for r, (num, ben, dt, pct) in enumerate(rows):
            self.table.setItem(r, 0, QTableWidgetItem(str(num)))
            self.table.setItem(r, 1, QTableWidgetItem(ben))
            self.table.setItem(r, 2, QTableWidgetItem(dt))
            self.table.setItem(r, 3, QTableWidgetItem(f"{pct:.2f}%"))
        self.table.resizeColumnsToContents()