# atajados_tab.py
from __future__ import annotations
import pandas as pd
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QPushButton,
    QDialog, QFormLayout, QLineEdit, QTableWidgetItem, QFileDialog,
    QMessageBox, QAbstractItemView, QHeaderView, QLabel
)
from database import Database


class AtajadosTab(QWidget):
    # ------------------------------------------------------------------ #
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.layout = QVBoxLayout(self)
        self._dirty = False
        self._loading = False

        # ───── NUEVO: etiqueta contador ─────
        self.count_lbl = QLabel()
        self.count_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.count_lbl.setStyleSheet("font-weight:bold;")
        self.layout.addWidget(self.count_lbl)

        # Toolbar
        toolbar = QHBoxLayout()
        self.import_btn = QPushButton("📥 Importar Atajados")
        self.add_btn    = QPushButton("➕ Registrar Atajado")
        self.del_btn    = QPushButton("🗑 Eliminar Atajado")
        self.save_btn   = QPushButton("✔ Confirmar")
        for w in (self.import_btn, self.add_btn, self.save_btn, self.del_btn):
            toolbar.addWidget(w)
        toolbar.addStretch()
        self.layout.addLayout(toolbar)

        # Tabla
        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.layout.addWidget(self.table)

        # Conexiones
        self.import_btn.clicked.connect(self.import_atajados)
        self.add_btn.clicked.connect(self.open_add)
        self.save_btn.clicked.connect(self.save_changes)
        self.del_btn.clicked.connect(self.delete_atajado)
        self.table.cellChanged.connect(self.on_cell_changed)

        self.refresh()

    # ------------------------------------------------------------------ #
    def refresh(self):
        """Carga todos los atajados y actualiza el contador."""
        self._loading = True
        rows = self.db.fetchall(
            "SELECT id, comunidad, number, beneficiario, ci, coord_e, coord_n FROM atajados"
        )
        self.table.clearContents()
        self.table.setRowCount(len(rows))
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Comunidad", "Atajado", "Nombre", "CI", "Este", "Norte"]
        )

        for r, (iid, com, num, ben, ci, e, n) in enumerate(rows):
            for c, val in enumerate((iid, com, num, ben, ci, e, n)):
                item = QTableWidgetItem(str(val))
                if c == 0:                                   # ID no editable
                    item.setFlags(item.flags() ^ Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(r, c, item)

        self._loading = False
        self._dirty   = False

        # ───── actualiza etiqueta contador ─────
        self.count_lbl.setText(f"<b>Total atajados: {len(rows)}</b>")

    # ------------------------------------------------------------------ #
    def import_atajados(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Importar Atajados", "", "Excel (*.xlsx);;CSV (*.csv)"
        )
        if not path:
            return
        try:
            df = (
                pd.read_excel(path)
                if path.lower().endswith(("xls", "xlsx"))
                else pd.read_csv(path)
            )
            # Columnas requeridas: 'COMUNIDAD','ATAJADO','NOMBRE','CI','ESTE','NORTE'
            repetidos = 0
            for _, row in df.iterrows():
                com = str(row.get("COMUNIDAD", "")).strip()
                num = str(row.get("ATAJADO", "")).replace("Atajado #", "").strip()
                ben = str(row.get("NOMBRE", "")).strip()
                ci  = str(row.get("CI", "")).strip()
                e   = float(row.get("ESTE", 0))
                n   = float(row.get("NORTE", 0))

                if self.db.fetchone("SELECT 1 FROM atajados WHERE number=?", (int(num),)):
                    repetidos += 1
                    continue

                self.db.execute(
                    "INSERT INTO atajados(comunidad, number, beneficiario, ci, coord_e, coord_n) "
                    "VALUES(?,?,?,?,?,?)",
                    (com, int(num), ben, ci, e, n)
                )
            self._dirty = True
            self.refresh()
            msg = "Atajados importados correctamente."
            if repetidos:
                msg += f"\n{repetidos} duplicados omitidos."
            QMessageBox.information(self, "Importación", msg)
        except Exception as ex:
            QMessageBox.critical(self, "Error de importación", f"No se pudo importar:\n{ex}")

    # ------------------------------------------------------------------ #
    def open_add(self):
        dlg = QDialog(self, windowTitle="Registrar Atajado")
        form = QFormLayout(dlg)
        com = QLineEdit(); num = QLineEdit(); ben = QLineEdit()
        ci  = QLineEdit(); e   = QLineEdit(); n   = QLineEdit()
        save = QPushButton("Guardar")
        for lbl, w in (
            ("Comunidad:", com), ("Atajado #:", num), ("Nombre:", ben),
            ("CI:", ci), ("Este:", e), ("Norte:", n)
        ):
            form.addRow(lbl, w)
        form.addRow(save)

        def on_save():
            try:
                if not com.text() or not ben.text():
                    raise ValueError
                if self.db.fetchone(
                    "SELECT 1 FROM atajados WHERE number=?", (int(num.text()),)
                ):
                    QMessageBox.warning(dlg, "Error", "Ese número de atajado ya existe.")
                    return
                self.db.execute(
                    "INSERT INTO atajados(comunidad, number, beneficiario, ci, coord_e, coord_n) "
                    "VALUES(?,?,?,?,?,?)",
                    (com.text(), int(num.text()), ben.text(), ci.text(),
                     float(e.text()), float(n.text()))
                )
                dlg.accept()
                self._dirty = True
                self.refresh()
            except ValueError:
                QMessageBox.warning(
                    dlg, "Error",
                    "Asegúrate de que todos los campos sean válidos y numéricos donde corresponda."
                )

        save.clicked.connect(on_save)
        dlg.exec()

    # ------------------------------------------------------------------ #
    def delete_atajado(self):
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            QMessageBox.information(self, "Eliminar", "Selecciona un atajado para eliminar.")
            return
        row = sel[0].row()
        iid = int(self.table.item(row, 0).text())
        if QMessageBox.question(
            self, "Confirmar", f"¿Eliminar atajado ID {iid}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            self.db.execute("DELETE FROM atajados WHERE id=?", (iid,))
            self._dirty = True
            self.refresh()

    # ------------------------------------------------------------------ #
    def on_cell_changed(self, row, col):
        if self._loading:
            return
        field_map = {
            1: "comunidad", 2: "number", 3: "beneficiario",
            4: "ci",        5: "coord_e", 6: "coord_n"
        }
        if col not in field_map:
            return
        iid  = int(self.table.item(row, 0).text())
        val  = self.table.item(row, col).text()
        field = field_map[col]
        try:
            if field in ("number", "coord_e", "coord_n"):
                val = float(val)
            self.db.execute(f"UPDATE atajados SET {field}=? WHERE id=?", (val, iid))
            self._dirty = True
        except ValueError:
            QMessageBox.warning(self, "Error", "Valor inválido.")

    # ------------------------------------------------------------------ #
    def save_changes(self):
        if not self._dirty:
            QMessageBox.information(self, "Confirmar", "No hay cambios pendientes.")
            return
        self._dirty = False
        QMessageBox.information(self, "Confirmar", "Cambios confirmados.")

    # ------------------------------------------------------------------ #
    def can_close(self) -> bool:
        if not self._dirty:
            return True
        res = QMessageBox.question(
            self, "Atajados sin guardar",
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
