from __future__ import annotations
import pandas as pd
from functools import partial
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QPushButton, QDialog, QFormLayout, QLineEdit, QTableWidgetItem,
    QFileDialog, QMessageBox, QAbstractItemView, QHeaderView,
    QComboBox, QGroupBox
)

from database import Database


class ItemsTab(QWidget):
    COL_ID, COL_CODE, COL_ACTIVO, COL_NAME, COL_UNIT, COL_QTY, COL_PU, COL_TOTAL, COL_PROGRESS, COL_ACTIONS = range(10)

    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self._loading = False
        self._dirty = False
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        grp = QGroupBox("Gestor de Ítems")
        head = QVBoxLayout(grp)
        self.note = QLabel("<i>Marca los ítems que quieras incluir en Seguimiento</i>")
        head.addWidget(self.note)

        toolbar = QHBoxLayout()
        self.import_btn = QPushButton("📥 Importar")
        self.add_btn = QPushButton("➕ Añadir")
        self.del_btn = QPushButton("🗑 Eliminar")
        self.save_btn = QPushButton("💾 Guardar")
        self.search = QLineEdit(placeholderText="Filtrar…")
        for w in (self.import_btn, self.add_btn, self.del_btn, self.save_btn, self.search):
            toolbar.addWidget(w)
        toolbar.addStretch()
        head.addLayout(toolbar)
        root.addWidget(grp)

        self.table = QTableWidget(selectionBehavior=QAbstractItemView.SelectionBehavior.SelectRows)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hdr.setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        root.addWidget(self.table)

        self.import_btn.clicked.connect(self._import_items)
        self.add_btn.clicked.connect(self._open_add)
        self.del_btn.clicked.connect(self._delete_selected)
        self.save_btn.clicked.connect(self.save_changes)
        self.table.cellChanged.connect(self._on_cell_edited)
        self.search.textChanged.connect(self._filter_rows)

    def refresh(self) -> None:
        self._loading = True
        rows = self.db.fetchall("SELECT id, code, name, unit, total, incidence, active, progress FROM items")
        self.table.setRowCount(len(rows))
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels([
            "ID", "Código", "Activo", "Nombre", "Unidad", "Cant.", "P.U.", "Total", "Avance (%)", "Acciones"
        ])
        for r, (iid, code, name, unit, qty, pu, active, progress) in enumerate(rows):
            itm_id = QTableWidgetItem(str(iid))
            itm_id.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(r, self.COL_ID, itm_id)

            self._add_editable(r, self.COL_CODE, code)

            combo_act = QComboBox()
            combo_act.addItems(["No", "Sí"])
            combo_act.setCurrentIndex(1 if active else 0)

            def _toggle_active(idx: int, iid=iid):
                self.db.execute("UPDATE items SET active=? WHERE id=?", (1 if idx == 1 else 0, iid))
                self._dirty = True

            combo_act.currentIndexChanged.connect(_toggle_active)
            self.table.setCellWidget(r, self.COL_ACTIVO, combo_act)

            for col, val in ((self.COL_NAME, name), (self.COL_UNIT, unit), (self.COL_QTY, qty), (self.COL_PU, pu)):
                self._add_editable(r, col, val)

            tot = QTableWidgetItem(str(qty * pu))
            tot.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(r, self.COL_TOTAL, tot)

            if active:
                avg = self.db.fetchone("SELECT AVG(quantity) FROM avances WHERE item_id=?", (iid,))[0] or 0
                pct_item = QTableWidgetItem(f"{avg:.0f}")
                pct_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self.table.setItem(r, self.COL_PROGRESS, pct_item)
            else:
                combo_pct = QComboBox()
                combo_pct.addItems(["0%", "25%", "50%", "75%", "100%"])
                combo_pct.setCurrentText(f"{int(progress)}%")

                def _update_pct(txt: str, iid=iid):
                    self.db.execute("UPDATE items SET progress=? WHERE id=?", (float(txt.rstrip('%')), iid))
                    self._dirty = True

                combo_pct.currentTextChanged.connect(_update_pct)
                self.table.setCellWidget(r, self.COL_PROGRESS, combo_pct)

            action_wgt = QWidget()
            alay = QHBoxLayout(action_wgt)
            btn_e = QPushButton("✏️", clicked=partial(self._edit_item, iid))
            btn_d = QPushButton("🗑", clicked=partial(self._delete_item_by_id, iid))
            for b in (btn_e, btn_d):
                alay.addWidget(b)
            alay.setContentsMargins(0, 0, 0, 0)
            self.table.setCellWidget(r, self.COL_ACTIONS, action_wgt)

        self._loading = False
        self._dirty = False

    def _add_editable(self, row: int, col: int, value: Any):
        item = QTableWidgetItem(str(value))
        item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, col, item)

    def _on_cell_edited(self, row: int, col: int) -> None:
        if self._loading:
            return
        if col not in (self.COL_CODE, self.COL_NAME, self.COL_UNIT, self.COL_QTY, self.COL_PU):
            return

        iid = int(self.table.item(row, self.COL_ID).text())
        val_txt = self.table.item(row, col).text()
        campo = {
            self.COL_CODE: "code", self.COL_NAME: "name",
            self.COL_UNIT: "unit", self.COL_QTY: "total",
            self.COL_PU: "incidence"
        }[col]

        try:
            val = float(val_txt) if campo in ("total", "incidence") else val_txt
            self.db.execute(f"UPDATE items SET {campo}=? WHERE id=?", (val, iid))
            self._dirty = True
        except ValueError:
            QMessageBox.warning(self, "Error", "Valor numérico inválido.")
            self.refresh()
            return

        if col in (self.COL_QTY, self.COL_PU):
            qty, pu = self.db.fetchone("SELECT total, incidence FROM items WHERE id=?", (iid,))
            self.table.item(row, self.COL_TOTAL).setText(str(qty * pu))

    def _import_items(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Importar Ítems", "", "Excel (*.xlsx);;CSV (*.csv)")
        if not path:
            return
        try:
            df = pd.read_excel(path) if path.lower().endswith(("xls", "xlsx")) else pd.read_csv(path)
            for _, row in df.iterrows():
                code = str(row.get("Numero", ""))[:20]
                name = row.get("Descripcion", "")
                unit = row.get("Unidad", "")
                qty = float(row.get("Cantidad", 0))
                pu = float(row.get("PrecioUnitario", 0))
                self.db.execute(
                    "INSERT INTO items(code,name,unit,total,incidence,active) VALUES(?,?,?,?,?,0)",
                    (code, name, unit, qty, pu)
                )
            self._dirty = True
            self.refresh()
            QMessageBox.information(self, "Importado", "Ítems importados correctamente.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo importar:\n{e}")

    def _open_add(self) -> None:
        dlg = QDialog(self, windowTitle="Añadir Ítem")
        form = QFormLayout(dlg)
        code_e = QLineEdit()
        name = QLineEdit()
        unit = QLineEdit()
        qty = QLineEdit()
        pu = QLineEdit()
        btn = QPushButton("Guardar")
        for lbl, w in (("Código:", code_e), ("Nombre:", name), ("Unidad:", unit), ("Cantidad:", qty), ("P. Unitario:", pu)):
            form.addRow(lbl, w)
        form.addRow(btn)

        def save():
            try:
                self.db.execute(
                    "INSERT INTO items(code,name,unit,total,incidence,active) VALUES(?,?,?,?,?,0)",
                    (code_e.text(), name.text(), unit.text(), float(qty.text()), float(pu.text()))
                )
                dlg.accept()
                self.refresh()
            except ValueError:
                QMessageBox.warning(dlg, "Error", "Cantidad y P.U. deben ser números.")

        btn.clicked.connect(save)
        dlg.exec()

    def _edit_item(self, iid: int) -> None:
        data = self.db.fetchall("SELECT code,name,unit,total,incidence FROM items WHERE id=?", (iid,))[0]
        dlg = QDialog(self, windowTitle=f"Editar Ítem {iid}")
        form = QFormLayout(dlg)
        code_e = QLineEdit(data[0])
        name_e = QLineEdit(data[1])
        unit_e = QLineEdit(data[2])
        qty_e = QLineEdit(str(data[3]))
        pu_e = QLineEdit(str(data[4]))
        btn = QPushButton("Actualizar")
        for lbl, w in (("Código:", code_e), ("Nombre:", name_e), ("Unidad:", unit_e), ("Cantidad:", qty_e), ("P. Unitario:", pu_e)):
            form.addRow(lbl, w)
        form.addRow(btn)

        def update():
            try:
                self.db.execute(
                    "UPDATE items SET code=?,name=?,unit=?,total=?,incidence=? WHERE id=?",
                    (code_e.text(), name_e.text(), unit_e.text(), float(qty_e.text()), float(pu_e.text()), iid)
                )
                dlg.accept()
                self.refresh()
            except ValueError:
                QMessageBox.warning(dlg, "Error", "Cantidad y P.U. deben ser números.")

        btn.clicked.connect(update)
        dlg.exec()

    def _delete_item_by_id(self, iid: int) -> None:
        reply = QMessageBox.question(
            self,
            "Confirmar",
            f"¿Eliminar ítem {iid}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.db.execute("DELETE FROM items WHERE id=?", (iid,))
            self.refresh()

    def _delete_selected(self) -> None:
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            QMessageBox.information(self, "Eliminar", "Selecciona al menos una fila.")
            return
        ids = [int(self.table.item(s.row(), self.COL_ID).text()) for s in sel]
        reply = QMessageBox.question(
            self,
            "Confirmar",
            f"¿Eliminar ítems {', '.join(map(str, ids))}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            for iid in ids:
                self.db.execute("DELETE FROM items WHERE id=?", (iid,))
            self.refresh()

    def _filter_rows(self, text: str) -> None:
        t = text.lower()
        for r in range(self.table.rowCount()):
            match = any(
                t in (self.table.item(r, c).text().lower() if self.table.item(r, c) else "")
                for c in range(self.table.columnCount())
            )
            self.table.setRowHidden(r, not match)

    def save_changes(self):
        if not self._dirty:
            QMessageBox.information(self, "Guardar", "No hay cambios pendientes.")
            return
        self._dirty = False
        QMessageBox.information(self, "Guardar", "Cambios de ítems guardados.")

    def can_close(self) -> bool:
        if not self._dirty:
            return True
        res = QMessageBox.question(
            self, "Ítems sin guardar",
            "Tienes cambios sin guardar. ¿Deseas guardarlos antes de salir?",
            QMessageBox.StandardButton.Save |
            QMessageBox.StandardButton.Discard |
            QMessageBox.StandardButton.Cancel
        )
        if res == QMessageBox.StandardButton.Save:
            self.save_changes()
            return True
        if res == QMessageBox.StandardButton.Discard:
            return True
        return False
