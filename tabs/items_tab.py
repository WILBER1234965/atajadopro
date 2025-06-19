# items_tab.py

"""
Pestaña «Ítems» – gestión de catálogo con desplegable Sí/No para ‘Activo’.
"""

import pandas as pd
from functools import partial
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QPushButton, QDialog, QFormLayout, QLineEdit, QTableWidgetItem,
    QFileDialog, QMessageBox, QAbstractItemView, QHeaderView,
    QComboBox, QGroupBox
)

from database import Database

# ---------- QSS local ----------
LIGHT_QSS = """
QWidget      { background:#ffffff; color:#202020; font-family:Segoe UI; font-size:12pt; }
QGroupBox    { border:1px solid #ccc; border-radius:10px; padding:10px; margin-top:6px; }
QPushButton  { background:#1976D2; color:#fff; border-radius:6px; padding:6px 14px; }
QPushButton:hover { background:#1259a4; }
QLineEdit    { background:#fafafa; border:1px solid #aaa; border-radius:6px; padding:5px; }
QTableWidget { background:#f9f9f9; alternate-background-color:#e8f0fe; color:#202020; border:1px solid #ccc; }
QHeaderView::section { background:#d0e8ff; color:#202020; font-weight:bold; padding:4px; border:1px solid #ccc; }
"""

DARK_QSS = """
QWidget      { background:#1e1e1e; color:#e0e0e0; font-family:Segoe UI; font-size:12pt; }
QGroupBox    { background:#252525; border:1px solid #444; border-radius:10px; padding:10px; margin-top:6px; }
QPushButton  { background:#0d6efd; color:#fff; border-radius:6px; padding:6px 14px; }
QPushButton:hover { background:#1a75ff; }
QLineEdit    { background:#2a2a2a; border:1px solid #555; border-radius:6px; padding:5px; color:#e0e0e0; }
QTableWidget { background:#272727; alternate-background-color:#1f1f1f; color:#e0e0e0; border:1px solid #444; }
QHeaderView::section { background:#353535; color:#e0e0e0; font-weight:bold; padding:4px; border:1px solid #444; }
"""


class ItemsTab(QWidget):
    """
    Pestaña de mantenimiento de ítems.
    Usa un QComboBox Sí/No para la columna ‘Activo’ y otro para ‘Avance (%)’
    cuando el ítem no está activo.
    """

    COL_ACTIVO = 1
    COL_NAME   = 2
    COL_UNIT   = 3
    COL_QTY    = 4
    COL_PU     = 5
    COL_TOTAL  = 6
    COL_PROGRESS = 7

    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self._loading = False

        self._build_ui()
        self.set_theme(False)
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # Header group
        group = QGroupBox("Gestor de Ítems")
        head = QVBoxLayout(group)
        self.note = QLabel("<i>Marca los ítems que quieras incluir en Seguimiento</i>")
        head.addWidget(self.note)

        toolbar = QHBoxLayout()
        self.import_btn = QPushButton("📥 Importar")
        self.add_btn    = QPushButton("➕ Añadir")
        self.del_btn    = QPushButton("🗑 Eliminar")
        self.search     = QLineEdit(placeholderText="Filtrar…")
        for w in (self.import_btn, self.add_btn, self.del_btn, self.search):
            toolbar.addWidget(w)
        toolbar.addStretch()
        head.addLayout(toolbar)
        root.addWidget(group)

        # Table
        self.table = QTableWidget(selectionBehavior=QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hdr.setStretchLastSection(True)
        root.addWidget(self.table)

        # Connections
        self.import_btn.clicked.connect(self._import_items)
        self.add_btn.clicked.connect(self._open_add)
        self.del_btn.clicked.connect(self._delete_item)
        self.table.cellChanged.connect(self._on_cell_edited)
        self.search.textChanged.connect(self._filter_rows)

    def set_theme(self, dark: bool) -> None:
        """Aplica tema claro u oscuro."""
        self.setStyleSheet(DARK_QSS if dark else LIGHT_QSS)
        self.note.setStyleSheet("color:#B0B0B0;" if dark else "color:#777777;")

    def refresh(self) -> None:
        """Recarga todos los ítems desde la BD."""
        self._loading = True
        rows = self.db.fetchall(
            "SELECT id, name, unit, total, incidence, active, progress FROM items"
        )

        self.table.setRowCount(len(rows))
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Activo", "Nombre", "Unidad", "Cant.", "P.U.", "Total", "Avance (%)"]
        )

        for r, (iid, name, unit, qty, pu, active, progress) in enumerate(rows):
            total = qty * pu

            # ID
            item_id = QTableWidgetItem(str(iid))
            item_id.setFlags(item_id.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(r, 0, item_id)

            # Activo: QComboBox Sí/No
            combo_act = QComboBox()
            combo_act.addItems(["No", "Sí"])
            combo_act.setCurrentIndex(1 if active else 0)
            combo_act.currentIndexChanged.connect(
                lambda idx, iid=iid: self.db.execute(
                    "UPDATE items SET active=? WHERE id=?",
                    (1 if idx == 1 else 0, iid)
                )
            )
            self.table.setCellWidget(r, self.COL_ACTIVO, combo_act)

            # Nombre, Unidad, Cantidad, P.U.
            for col, val in (
                (self.COL_NAME, name),
                (self.COL_UNIT, unit),
                (self.COL_QTY, qty),
                (self.COL_PU, pu),
            ):
                it = QTableWidgetItem(str(val))
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(r, col, it)

            # Total (solo lectura)
            it_tot = QTableWidgetItem(str(total))
            it_tot.setFlags(it_tot.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(r, self.COL_TOTAL, it_tot)

            # Avance (%)
            if active:
                avg = self.db.fetchall(
                    "SELECT AVG(quantity) FROM avances WHERE item_id=?", (iid,)
                )[0][0] or 0
                it_avg = QTableWidgetItem(f"{avg:.0f}")
                it_avg.setFlags(it_avg.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(r, self.COL_PROGRESS, it_avg)
            else:
                combo_pct = QComboBox()
                combo_pct.addItems(["0%", "25%", "50%", "75%", "100%"])
                combo_pct.setCurrentText(f"{int(progress)}%")
                combo_pct.currentTextChanged.connect(
                    lambda txt, iid=iid: self.db.execute(
                        "UPDATE items SET progress=? WHERE id=?",
                        (float(txt.replace("%", "")), iid)
                    )
                )
                self.table.setCellWidget(r, self.COL_PROGRESS, combo_pct)

        self._loading = False

    def _on_cell_edited(self, row: int, col: int) -> None:
        """Guarda cambios en Nombre, Unidad, Cantidad o P.U."""
        if self._loading or col not in (self.COL_NAME, self.COL_UNIT, self.COL_QTY, self.COL_PU):
            return

        iid = int(self.table.item(row, 0).text())
        campo_map = {
            self.COL_NAME: "name",
            self.COL_UNIT: "unit",
            self.COL_QTY:  "total",
            self.COL_PU:   "incidence",
        }
        campo = campo_map[col]
        val_txt = self.table.item(row, col).text()
        try:
            val = float(val_txt) if campo in ("total", "incidence") else val_txt
            self.db.execute(f"UPDATE items SET {campo}=? WHERE id=?", (val, iid))
        except ValueError:
            QMessageBox.warning(self, "Error", "Valor numérico inválido.")
            self.refresh()
            return

        # Actualizar total
        qty, pu = self.db.fetchall(
            "SELECT total, incidence FROM items WHERE id=?", (iid,)
        )[0]
        self.table.item(row, self.COL_TOTAL).setText(str(qty * pu))

    def _import_items(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Importar Ítems", "", "Excel (*.xlsx);;CSV (*.csv)"
        )
        if not path:
            return
        try:
            df = (
                pd.read_excel(path)
                if path.lower().endswith(("xls", "xlsx"))
                else pd.read_csv(path)
            )
            for _, row in df.iterrows():
                self.db.execute(
                    "INSERT INTO items(name, unit, total, incidence, active) VALUES(?,?,?,?,0)",
                    (
                        row.get("DESCRIPCIÓN", ""),
                        row.get("UNIDAD", ""),
                        float(row.get("CANT.", 0)),
                        float(row.get("P.U.", 0)),
                    ),
                )
            self.refresh()
            QMessageBox.information(self, "Importado", "Ítems importados correctamente.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo importar:\n{e}")

    def _open_add(self) -> None:
        dlg = QDialog(self, windowTitle="Añadir Ítem")
        form = QFormLayout(dlg)
        name, unit, qty, pu = QLineEdit(), QLineEdit(), QLineEdit(), QLineEdit()
        btn = QPushButton("Guardar")
        for lbl, w in (("Nombre:", name), ("Unidad:", unit), ("Cantidad:", qty), ("P. Unitario:", pu)):
            form.addRow(lbl, w)
        form.addRow(btn)

        def save():
            try:
                self.db.execute(
                    "INSERT INTO items(name,unit,total,incidence,active) VALUES(?,?,?,?,0)",
                    (name.text(), unit.text(), float(qty.text()), float(pu.text())),
                )
                dlg.accept()
                self.refresh()
            except ValueError:
                QMessageBox.warning(dlg, "Error", "Cantidad y P.U. deben ser números.")

        btn.clicked.connect(save)
        dlg.exec()

    def _delete_item(self) -> None:
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            QMessageBox.information(self, "Eliminar", "Selecciona una fila.")
            return
        row = sel[0].row()
        iid = int(self.table.item(row, 0).text())
        if QMessageBox.question(
            self, "Confirmar", f"¿Eliminar ítem {iid}?", QMessageBox.Yes | QMessageBox.No
        ) == QMessageBox.Yes:
            self.db.execute("DELETE FROM items WHERE id=?", (iid,))
            self.refresh()

    def _filter_rows(self, text: str) -> None:
        """Oculta filas cuyo texto no coincida con el filtro."""
        t = text.lower()
        for r in range(self.table.rowCount()):
            match = any(
                t in (
                    self.table.item(r, c).text().lower() if self.table.item(r, c) else ""
                )
                for c in range(self.table.columnCount())
            )
            self.table.setRowHidden(r, not match)
