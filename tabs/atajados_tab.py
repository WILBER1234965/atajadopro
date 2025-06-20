# atajados_tab.py
import os
import pandas as pd
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QPushButton,
    QDialog, QFormLayout, QLineEdit, QTableWidgetItem, QFileDialog,
    QMessageBox, QAbstractItemView, QHeaderView
)
from PyQt6.QtCore import Qt
from database import Database

class AtajadosTab(QWidget):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.layout = QVBoxLayout(self)
        self._dirty = False

        # Toolbar con Importar, Añadir, Guardar y Eliminar
        toolbar = QHBoxLayout()
        self.import_btn = QPushButton("📥 Importar Atajados")
        self.add_btn    = QPushButton("➕ Registrar Atajado")
        self.del_btn    = QPushButton("🗑 Eliminar Atajado")
        self.save_btn   = QPushButton("💾 Guardar Cambios")
        for w in (self.import_btn, self.add_btn, self.save_btn, self.del_btn):
            toolbar.addWidget(w)

        toolbar.addStretch()
        self.layout.addLayout(toolbar)

        # Tabla de atajados
        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
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

        self._loading = False
        self.refresh()

    def refresh(self):
        """Carga todos los atajados (sin fechas ni estado)."""
        self._loading = True
        rows = self.db.fetchall(
            "SELECT id, comunidad, number, beneficiario, ci, coord_e, coord_n FROM atajados"
        )
        self.table.clearContents()
        self.table.setRowCount(len(rows))
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "ID", "Comunidad", "Atajado", "Nombre", "CI", "Este", "Norte"
        ])
        for r, (iid, com, num, ben, ci, e, n) in enumerate(rows):
            vals = [iid, com, num, ben, ci, e, n]
            for c, val in enumerate(vals):
                item = QTableWidgetItem(str(val))
                # ID no editable
                if c == 0:
                    item.setFlags(item.flags() ^ Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(r, c, item)
        self._loading = False
        self._dirty = False

    def import_atajados(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Importar Atajados", "", "Excel (*.xlsx);;CSV (*.csv)"
        )
        if not path:
            return
        try:
            df = pd.read_excel(path) if path.lower().endswith(("xls", "xlsx")) else pd.read_csv(path)
            # Columnas: 'COMUNIDAD','ATAJADO','NOMBRE','CI','ESTE','NORTE'
            for _, row in df.iterrows():
                com = str(row.get("COMUNIDAD","")).strip()
                num = str(row.get("ATAJADO","")).replace("Atajado #","").strip()
                ben = str(row.get("NOMBRE","")).strip()
                ci  = str(row.get("CI","")).strip()
                e   = float(row.get("ESTE",0))
                n   = float(row.get("NORTE",0))
                self.db.execute(
                    "INSERT INTO atajados(comunidad, number, beneficiario, ci, coord_e, coord_n) VALUES(?,?,?,?,?,?)",
                    (com, int(num), ben, ci, e, n)
                )
            self.refresh()
            self._dirty = True
            QMessageBox.information(self, "Importación", "Atajados importados correctamente.")
        except Exception as ex:
            QMessageBox.critical(self, "Error de importación", f"No se pudo importar:\n{ex}")

    def open_add(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Registrar Atajado")
        form = QFormLayout(dlg)
        com = QLineEdit()
        num = QLineEdit()
        ben = QLineEdit()
        ci  = QLineEdit()
        e   = QLineEdit()
        n   = QLineEdit()
        save = QPushButton("Guardar")
        form.addRow("Comunidad:", com)
        form.addRow("Atajado #:", num)
        form.addRow("Nombre:", ben)
        form.addRow("CI:", ci)
        form.addRow("Este:", e)
        form.addRow("Norte:", n)
        form.addRow(save)

        def on_save():
            try:
                if not com.text() or not ben.text():
                    raise ValueError               
                self.db.execute(
                    "INSERT INTO atajados(comunidad, number, beneficiario, ci, coord_e, coord_n) VALUES(?,?,?,?,?,?)",
                    (com.text(), int(num.text()), ben.text(), ci.text(),
                     float(e.text()), float(n.text()))
                )
                dlg.accept()
                self.refresh()
                self._dirty = True                
            except ValueError:
                QMessageBox.warning(dlg, "Error", "Asegúrate de que todos los campos sean válidos y numéricos donde corresponda.")

        save.clicked.connect(on_save)
        dlg.exec()

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
            self.refresh()
            self._dirty = True            

    def on_cell_changed(self, row, col):
        if self._loading:
            return
        # Mapear columnas editables a campos
        field_map = {
            1: "comunidad",
            2: "number",
            3: "beneficiario",
            4: "ci",
            5: "coord_e",
            6: "coord_n"
        }
        if col not in field_map:
            return
        iid = int(self.table.item(row, 0).text())
        val = self.table.item(row, col).text()
        field = field_map[col]
        try:
            if field in ("number", "coord_e", "coord_n"):
                val = float(val)
            self.db.execute(f"UPDATE atajados SET {field}=? WHERE id=?", (val, iid))
            self._dirty = True
        except ValueError:
            QMessageBox.warning(self, "Error", "Valor inválido.")

    # ------------------------------------------------------------------
    def save_changes(self):
        if not self._dirty:
            QMessageBox.information(self, "Guardar", "No hay cambios pendientes.")
            return
        self._dirty = False
        QMessageBox.information(self, "Guardar", "Cambios de atajados guardados.")

    # ------------------------------------------------------------------
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