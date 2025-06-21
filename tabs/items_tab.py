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
    # Índices de columna
    COL_ID, COL_CODE, COL_ACTIVO, COL_NAME, COL_UNIT, \
    COL_QTY, COL_PU, COL_TOTAL, COL_PROGRESS, COL_ACTIONS = range(10)

    # ------------------------------------------------------------------ #
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self._loading = False          # bloquea señales durante carga
        self._dirty   = False          # cambios pendientes de guardar
        self._atajados_total = 1       # se actualiza en refresh()
        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        grp = QGroupBox("Gestor de Ítems")
        head = QVBoxLayout(grp)
        head.addWidget(QLabel("<i>Marca los ítems que quieras incluir en Seguimiento</i>"))

        toolbar = QHBoxLayout()
        self.import_btn = QPushButton("📥 Importar")
        self.add_btn    = QPushButton("➕ Añadir")
        self.del_btn    = QPushButton("🗑 Eliminar")
        self.save_btn   = QPushButton("✔ Confirmar")
        self.search     = QLineEdit(placeholderText="Filtrar…")
        for w in (self.import_btn, self.add_btn, self.del_btn, self.save_btn, self.search):
            toolbar.addWidget(w)
        toolbar.addStretch()
        head.addLayout(toolbar)
        root.addWidget(grp)

        # tabla
        self.table = QTableWidget(selectionBehavior=QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hdr.setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        root.addWidget(self.table)

        # total Bs
        self.total_lbl = QLabel(alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.total_lbl.setStyleSheet("font-weight:bold;")
        root.addWidget(self.total_lbl)

        # señales
        self.import_btn.clicked.connect(self._import_items)
        self.add_btn.clicked.connect(self._open_add)
        self.del_btn.clicked.connect(self._delete_selected)
        self.save_btn.clicked.connect(self.save_changes)
        self.table.cellChanged.connect(self._on_cell_edited)
        self.search.textChanged.connect(self._filter_rows)

    # ------------------------------------------------------------------ #
    # REFRESH
    # ------------------------------------------------------------------ #
    def refresh(self) -> None:
        """Recarga los ítems y actualiza la tabla."""
        self._loading = True

        # nº total de atajados (para porcentaje global)
        self._atajados_total = self.db.fetchone("SELECT COUNT(*) FROM atajados")[0] or 1

        rows = self.db.fetchall(
            "SELECT id, code, name, unit, total, incidence, active, progress "
            "FROM items"
        )

        self.table.setRowCount(len(rows))
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels([
            "ID", "Número", "Activo", "Nombre", "Unidad",
            "Cant.", "P.U.", "Total", "Avance (%)", "Acciones"
        ])

        for r, (iid, code, name, unit, qty, pu, active, progress) in enumerate(rows):
            self._add_editable(r, self.COL_ID, iid, editable=False)
            self._add_editable(r, self.COL_CODE, code)

            combo_act = QComboBox(); combo_act.addItems(["No", "Sí"])
            combo_act.setCurrentIndex(1 if active else 0)
            combo_act.currentIndexChanged.connect(
                lambda idx, row=r, iid=iid: self._toggle_active(idx, row, iid))
            self.table.setCellWidget(r, self.COL_ACTIVO, combo_act)

            for col, val in (
                (self.COL_NAME, name),
                (self.COL_UNIT, unit),
                (self.COL_QTY,  qty),
                (self.COL_PU,   pu)
            ):
                self._add_editable(r, col, val)

            self._add_editable(r, self.COL_TOTAL, qty * pu, editable=False)
            self._configurar_celda_avance(r, iid, bool(active), progress)
            self._crear_celda_acciones(r, iid)

        self._loading = False
        self._dirty   = False
        self._actualizar_total()

    # ------------------------------------------------------------------ #
    # Helpers de celdas
    # ------------------------------------------------------------------ #
    def _add_editable(self, row: int, col: int, value: Any, *, editable: bool = True):
        itm = QTableWidgetItem(str(value))
        flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
        if editable:
            flags |= Qt.ItemFlag.ItemIsEditable
        itm.setFlags(flags)
        self.table.setItem(row, col, itm)

    def _crear_celda_acciones(self, row: int, iid: int):
        cont = QWidget()
        lay = QHBoxLayout(cont); lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(QPushButton("✏️", clicked=partial(self._edit_item, iid)))
        lay.addWidget(QPushButton("🗑", clicked=partial(self._delete_item_by_id, iid)))
        self.table.setCellWidget(row, self.COL_ACTIONS, cont)

    # ------------------------------------------------------------------ #
    # Cálculo GLOBAL del avance
    # ------------------------------------------------------------------ #
    def _calc_global_pct(self, iid: int) -> float:
        """
        Porcentaje global =  (Σ quantity ejecutada) / N_atajados

        - Cada registro de avance almacena 0-100 (% del ítem por atajado).
        - Si 2 atajados de 100 dan 100 %, SUM = 200 -> 200/total_atajados.
        """
        ejecutado = self.db.fetchone(
            "SELECT COALESCE(SUM(quantity),0) FROM avances WHERE item_id=?", (iid,)
        )[0] or 0.0
        pct = ejecutado / self._atajados_total  # ya es porcentaje
        return round(min(pct, 100), 0)

    def _configurar_celda_avance(self, row: int, iid: int, active: bool, progress: float):
        self.table.removeCellWidget(row, self.COL_PROGRESS)
        self.table.takeItem(row, self.COL_PROGRESS)

        if active:
            pct = self._calc_global_pct(iid)
            itm = QTableWidgetItem(f"{pct:.2f}%") 
            itm.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(row, self.COL_PROGRESS, itm)
        else:
            combo = QComboBox(); combo.addItems(["0%", "25%", "50%", "75%", "100%"])
            combo.setCurrentText(f"{int(progress)}%")
            combo.currentTextChanged.connect(lambda t, iid=iid: self._update_pct(t, iid))
            self.table.setCellWidget(row, self.COL_PROGRESS, combo)

    # ------------------------------------------------------------------ #
    # Cambios en “Activo”
    # ------------------------------------------------------------------ #
    def _toggle_active(self, idx: int, row: int, iid: int):
        self.db.execute("UPDATE items SET active=? WHERE id=?", (1 if idx else 0, iid))
        prog = self.db.fetchone("SELECT progress FROM items WHERE id=?", (iid,))[0]
        self._configurar_celda_avance(row, iid, bool(idx), prog)
        self._dirty = True

    # ------------------------------------------------------------------ #
    # Combo de avance editable
    # ------------------------------------------------------------------ #
    def _update_pct(self, txt: str, iid: int):
        self.db.execute("UPDATE items SET progress=? WHERE id=?",
                        (float(txt.rstrip('%')), iid))
        self._dirty = True

    # ------------------------------------------------------------------ #
    # Edición directa de otras columnas
    # ------------------------------------------------------------------ #
    def _on_cell_edited(self, row: int, col: int) -> None:
        if self._loading or col not in (self.COL_CODE, self.COL_NAME, self.COL_UNIT,
                                        self.COL_QTY, self.COL_PU):
            return
        iid  = int(self.table.item(row, self.COL_ID).text())
        text = self.table.item(row, col).text()
        campo = {self.COL_CODE:"code", self.COL_NAME:"name", self.COL_UNIT:"unit",
                 self.COL_QTY:"total", self.COL_PU:"incidence"}[col]
        try:
            val = float(text) if campo in ("total", "incidence") else text
            self.db.execute(f"UPDATE items SET {campo}=? WHERE id=?", (val, iid))
            self._dirty = True
        except ValueError:
            QMessageBox.warning(self, "Error", "Valor numérico inválido.")
            self.refresh(); return

        if col in (self.COL_QTY, self.COL_PU):
            qty, pu = self.db.fetchone(
                "SELECT total, incidence FROM items WHERE id=?", (iid,))
            self.table.item(row, self.COL_TOTAL).setText(str(qty * pu))
            self._actualizar_total()

    # ------------------------------------------------------------------ #
    # Importar ítems
    # ------------------------------------------------------------------ #
    def _import_items(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Importar Ítems", "", "Excel (*.xlsx *.xls);;CSV (*.csv)"
        )
        if not path:
            return
        try:
            df = pd.read_excel(path) if path.lower().endswith(("xls", "xlsx")) \
                 else pd.read_csv(path)
            for _, row in df.iterrows():
                code = str(row.get("Numero", ""))[:20]
                name = row.get("Descripcion", "")
                unit = row.get("Unidad", "")
                qty  = float(row.get("Cantidad", 0))
                pu   = float(row.get("PrecioUnitario", 0))
                self.db.execute(
                    "INSERT INTO items(code,name,unit,total,incidence,active)"
                    "VALUES(?,?,?,?,?,0)",
                    (code, name, unit, qty, pu)
                )
            self.refresh()
            QMessageBox.information(self, "Importado", "Ítems importados correctamente.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo importar:\n{e}")

    # ------------------------------------------------------------------ #
    # Añadir ítem manual
    # ------------------------------------------------------------------ #
    def _open_add(self) -> None:
        dlg  = QDialog(self, windowTitle="Añadir Ítem")
        form = QFormLayout(dlg)
        code_e = QLineEdit(); name_e = QLineEdit(); unit_e = QLineEdit()
        qty_e  = QLineEdit(); pu_e   = QLineEdit()
        for lbl, w in (("Número:", code_e), ("Nombre:", name_e), ("Unidad:", unit_e),
                       ("Cantidad:", qty_e), ("P. Unitario:", pu_e)):
            form.addRow(lbl, w)
        btn = QPushButton("Guardar"); form.addRow(btn)

        def save():
            try:
                if self.db.fetchone("SELECT 1 FROM items WHERE code=?", (code_e.text(),)):
                    QMessageBox.warning(dlg, "Duplicado", "Ese número ya existe."); return
                self.db.execute(
                    "INSERT INTO items(code,name,unit,total,incidence,active)"
                    "VALUES(?,?,?,?,?,0)",
                    (code_e.text(), name_e.text(), unit_e.text(),
                     float(qty_e.text()), float(pu_e.text()))
                )
                dlg.accept(); self.refresh()
            except ValueError:
                QMessageBox.warning(dlg, "Error", "Cantidad y P.U. deben ser números.")
        btn.clicked.connect(save); dlg.exec()

    # ------------------------------------------------------------------ #
    # Editar ítem
    # ------------------------------------------------------------------ #
    def _edit_item(self, iid: int) -> None:
        code, name, unit, qty, pu = self.db.fetchone(
            "SELECT code,name,unit,total,incidence FROM items WHERE id=?", (iid,)
        )
        dlg  = QDialog(self, windowTitle=f"Editar Ítem {iid}")
        form = QFormLayout(dlg)
        code_e = QLineEdit(code); name_e = QLineEdit(name); unit_e = QLineEdit(unit)
        qty_e  = QLineEdit(str(qty)); pu_e = QLineEdit(str(pu))
        for lbl, w in (("Número:", code_e), ("Nombre:", name_e), ("Unidad:", unit_e),
                       ("Cantidad:", qty_e), ("P. Unitario:", pu_e)):
            form.addRow(lbl, w)
        btn = QPushButton("Actualizar"); form.addRow(btn)

        def update():
            try:
                if self.db.fetchone(
                    "SELECT 1 FROM items WHERE code=? AND id<>?", (code_e.text(), iid)
                ):
                    QMessageBox.warning(dlg, "Duplicado", "Ese número ya existe."); return
                self.db.execute(
                    "UPDATE items SET code=?,name=?,unit=?,total=?,incidence=? WHERE id=?",
                    (code_e.text(), name_e.text(), unit_e.text(),
                     float(qty_e.text()), float(pu_e.text()), iid)
                )
                dlg.accept(); self.refresh()
            except ValueError:
                QMessageBox.warning(dlg, "Error", "Cantidad y P.U. deben ser números.")
        btn.clicked.connect(update); dlg.exec()

    # ------------------------------------------------------------------ #
    # Eliminar ítem
    # ------------------------------------------------------------------ #
    def _delete_item_by_id(self, iid: int) -> None:
        if QMessageBox.question(
            self, "Confirmar", f"¿Eliminar ítem {iid}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            self.db.execute("DELETE FROM items WHERE id=?", (iid,)); self.refresh()

    # ------------------------------------------------------------------ #
    # Eliminar seleccionados
    # ------------------------------------------------------------------ #
    def _delete_selected(self) -> None:
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            QMessageBox.information(self, "Eliminar", "Selecciona al menos una fila."); return
        ids = [int(self.table.item(s.row(), self.COL_ID).text()) for s in sel]
        if QMessageBox.question(
            self, "Confirmar", f"¿Eliminar ítems {', '.join(map(str, ids))}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            for iid in ids:
                self.db.execute("DELETE FROM items WHERE id=?", (iid,))
            self.refresh()

    # ------------------------------------------------------------------ #
    # Filtro
    # ------------------------------------------------------------------ #
    def _filter_rows(self, text: str) -> None:
        t = text.lower()
        for r in range(self.table.rowCount()):
            match = any(
                t in (self.table.item(r, c).text().lower() if self.table.item(r, c) else "")
                for c in range(self.table.columnCount())
            )
            self.table.setRowHidden(r, not match)

    # ------------------------------------------------------------------ #
    # Total Bs
    # ------------------------------------------------------------------ #
    def _actualizar_total(self):
        total = 0.0
        for r in range(self.table.rowCount()):
            try:
                total += float(self.table.item(r, self.COL_TOTAL).text())
            except Exception:
                pass
        self.total_lbl.setText(f"<b>Precio total: Bs {total:,.2f}</b>")

    # ------------------------------------------------------------------ #
    # Guardar / confirmar
    # ------------------------------------------------------------------ #
    def save_changes(self):
        if not self._dirty:
            QMessageBox.information(self, "Confirmar", "No hay cambios pendientes."); return
        self._dirty = False
        QMessageBox.information(self, "Confirmar", "Cambios confirmados.")

    # ------------------------------------------------------------------ #
    # Cierre
    # ------------------------------------------------------------------ #
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
            self.save_changes(); return True
        if res == QMessageBox.StandardButton.Discard:
            return True
        return False
