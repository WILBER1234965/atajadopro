"""
Pestaña de registro de avances de obra.
Incluye selector de atajado, tabla de ítems, carga de imágenes y guardado.
"""

import os
import shutil
from datetime import datetime
from pathlib import Path

import sqlite3
import pandas as pd
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QCompleter,
    QTableWidget, QTableWidgetItem, QPushButton, QFileDialog, QMessageBox,
    QListWidget, QListWidgetItem, QDialog, QScrollArea, QDateEdit, QLineEdit,
    QHeaderView
)
from PyQt6.QtCore import Qt, QSize, QDate
from PyQt6.QtGui import QPixmap, QIcon

from database import Database, IMAGES_DIR


# --------------------------------------------------------------------------- #
#                                Vista previa                                 #
# --------------------------------------------------------------------------- #
class ImagePreviewDialog(QDialog):
    def __init__(self, image_paths, index=0):
        super().__init__()
        self.image_paths = image_paths
        self.index = index

        self.setWindowTitle("Vista Previa")
        self.setWindowState(Qt.WindowState.WindowMaximized)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )

        main_layout = QVBoxLayout(self)

        # Navegación
        nav = QHBoxLayout()
        self.prev_btn = QPushButton("◀")
        self.prev_btn.clicked.connect(self.show_prev)
        nav.addWidget(self.prev_btn)
        nav.addStretch()
        self.next_btn = QPushButton("▶")
        self.next_btn.clicked.connect(self.show_next)
        nav.addWidget(self.next_btn)
        main_layout.addLayout(nav)

        # Área de imagen
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.label = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.scroll.setWidget(self.label)
        main_layout.addWidget(self.scroll)

        self._load_pixmap()

    # ---------- Navegación ----------
    def show_prev(self):
        self.index = (self.index - 1) % len(self.image_paths)
        self._load_pixmap()

    def show_next(self):
        self.index = (self.index + 1) % len(self.image_paths)
        self._load_pixmap()

    # ---------- Redimensionado ----------
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_pixmap()

    # ---------- Helpers internos ----------
    def _load_pixmap(self):
        pix = QPixmap(self.image_paths[self.index])
        self._original = pix
        self._update_pixmap()

    def _update_pixmap(self):
        if hasattr(self, "_original") and not self._original.isNull():
            area = self.scroll.viewport().size()
            scaled = self._original.scaled(
                area,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.label.setPixmap(scaled)


# --------------------------------------------------------------------------- #
#                                   Pestaña                                   #
# --------------------------------------------------------------------------- #
class AvanceTab(QWidget):
    def __init__(self, db: Database, save_callback=None):
        super().__init__()
        self.db = db
        self.current_atajado: int | None = None
        self._save_callback = save_callback

        root = QVBoxLayout(self)

        # ---------- Selector de atajado ----------
        sel = QHBoxLayout()
        sel.addWidget(QLabel("Atajado / Beneficiario:"))

        self.at_combo = QComboBox()
        self._populate_atajado_combo()
        self.at_combo.setEditable(True)
        completer = QCompleter(
            [self.at_combo.itemText(i) for i in range(self.at_combo.count())]
        )
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.at_combo.setCompleter(completer)
        sel.addWidget(self.at_combo)

        self.load_btn = QPushButton("Cargar Ítems")
        self.load_btn.clicked.connect(self.load_items)
        sel.addWidget(self.load_btn)
        root.addLayout(sel)

        # ---------- Tabla de ítems ----------
        self.table = QTableWidget()
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hdr.setStretchLastSection(True)
        root.addWidget(self.table)

        # ---------- Botones de acción ----------
        actions = QHBoxLayout()
        self.img_btn = QPushButton("📎 Adjuntar Imágenes")
        self.img_btn.clicked.connect(self.attach_images)
        self.save_btn = QPushButton("💾 Guardar Avance")
        self.save_btn.clicked.connect(self.save_progress)
        actions.addWidget(self.img_btn)
        actions.addWidget(self.save_btn)
        actions.addStretch()
        root.addLayout(actions)

        # ---------- Lista de miniaturas ----------
        self.img_list = QListWidget(viewMode=QListWidget.ViewMode.IconMode)
        self.img_list.setIconSize(QSize(100, 100))
        self.img_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.img_list.itemDoubleClicked.connect(self.preview_image)
        root.addWidget(self.img_list)

        # Primer estado
        if self.at_combo.count() == 0:
            self._disable_controls_initial()
        else:
            self.load_items()

    # =======================================================================
    #                              Helpers                                   #
    # =======================================================================
    def _populate_atajado_combo(self):
        ats = self.db.fetchall("SELECT number, beneficiario FROM atajados")
        self.at_combo.addItems([f"{num} – {ben}" for num, ben in ats])

    def _disable_controls_initial(self):
        """Desactiva controles y muestra indicación cuando no hay atajados."""
        self.load_btn.setEnabled(False)
        self.img_btn.setEnabled(False)
        self.save_btn.setEnabled(False)
        self.table.setDisabled(True)
        QMessageBox.information(
            self,
            "Sin atajados",
            "Primero debes crear un atajado en la pestaña 'Atajados' para registrar avances."
        )

    # =======================================================================
    #                     Carga y visualización de ítems                     #
    # =======================================================================
    def load_items(self):
        text = self.at_combo.currentText().strip()
        if not text or "–" not in text:
            QMessageBox.warning(self, "Selección inválida", "Selecciona un atajado válido.")
            return
        try:
            num = int(text.split("–")[0].strip())
        except ValueError:
            QMessageBox.warning(self, "Selección inválida", "Selecciona un atajado válido.")
            return

        self.current_atajado = num

        # ---------- Datos ----------
        at_count = self.db.fetchall("SELECT COUNT(*) FROM atajados")[0][0] or 1
        rows = self.db.fetchall(
            "SELECT id, name, total, incidence FROM items WHERE active=1"
        )

        headers = [
            "ID", "Nombre", "Cant.", "P.U.", "Total",
            "Act. Fechas", "Inicio", "Fin",
            "Comentario", "Avance (%)"
        ]

        self.table.blockSignals(True)
        self.table.clear()
        self.table.setRowCount(len(rows))
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        for r, (iid, name, total_qty, unit_price) in enumerate(rows):
            qty = total_qty / at_count
            cost_total = qty * unit_price

            # ID, Nombre, Cantidad, PU, Total
            self.table.setItem(r, 0, QTableWidgetItem(str(iid)))
            self.table.setItem(r, 1, QTableWidgetItem(name))
            self.table.setItem(r, 2, QTableWidgetItem(f"{qty:.2f}"))
            self.table.setItem(r, 3, QTableWidgetItem(str(unit_price)))
            self.table.setItem(r, 4, QTableWidgetItem(f"{cost_total:.2f}"))

            # Check fechas
            chk = QTableWidgetItem()
            chk.setFlags(chk.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            chk.setCheckState(Qt.CheckState.Unchecked)
            self.table.setItem(r, 5, chk)

            # Fechas inicio/fin
            inicio = QDateEdit(calendarPopup=True, enabled=False)
            fin = QDateEdit(calendarPopup=True, enabled=False)
            self.table.setCellWidget(r, 6, inicio)
            self.table.setCellWidget(r, 7, fin)

            # Comentario
            self.table.setCellWidget(r, 8, QLineEdit())

            # Avance %
            combo = QComboBox()
            combo.addItems(["0%", "25%", "50%", "75%", "100%"])
            self.table.setCellWidget(r, 9, combo)

            # Cargar avance previo
            rec = self.db.fetchall(
                "SELECT quantity, start_date, end_date FROM avances "
                "WHERE atajado_id=? AND item_id=?",
                (num, iid)
            )
            if rec:
                pct_saved, sd, ed = rec[0]
                combo.setCurrentText(f"{int(pct_saved)}%")
                if sd and ed:
                    chk.setCheckState(Qt.CheckState.Checked)
                    inicio.setEnabled(True)
                    fin.setEnabled(True)
                    inicio.setDate(QDate.fromString(sd, "yyyy-MM-dd"))
                    fin.setDate(QDate.fromString(ed, "yyyy-MM-dd"))

        self.table.cellChanged.connect(self.on_cell_changed)
        self.table.blockSignals(False)

        # ---------- Miniaturas ----------
        self.img_list.clear()
        img_dir = IMAGES_DIR / str(num)
        if img_dir.is_dir():
            for f in sorted(img_dir.iterdir()):
                if f.is_file():
                    pix = QPixmap(str(f))
                    if not pix.isNull():
                        item = QListWidgetItem()
                        item.setIcon(QIcon(pix))
                        item.setData(Qt.ItemDataRole.UserRole, str(f))
                        self.img_list.addItem(item)

    # =======================================================================
    #                              Eventos                                   #
    # =======================================================================
    def on_cell_changed(self, row: int, col: int):
        if col == 5:  # check Activar fechas
            state = self.table.item(row, 5).checkState()
            enab = state == Qt.CheckState.Checked
            for c in (6, 7):
                w = self.table.cellWidget(row, c)
                if w:
                    w.setEnabled(enab)

    # =======================================================================
    #                          Adjuntar imágenes                             #
    # =======================================================================
    def attach_images(self):
        if self.current_atajado is None:
            QMessageBox.warning(self, "Error", "Carga primero un atajado.")
            return

        paths, _ = QFileDialog.getOpenFileNames(
            self, "Seleccionar imágenes", "", "Images (*.png *.jpg *.jpeg)"
        )
        if not paths:
            return

        img_dir = IMAGES_DIR / str(self.current_atajado)
        img_dir.mkdir(parents=True, exist_ok=True)

        for p in paths:
            dst = img_dir / f"{datetime.now().timestamp()}_{Path(p).name}"
            shutil.copy(p, dst)
            pix = QPixmap(str(dst))
            if not pix.isNull():
                item = QListWidgetItem()
                item.setIcon(QIcon(pix))
                item.setData(Qt.ItemDataRole.UserRole, str(dst))
                self.img_list.addItem(item)

    # =======================================================================
    #                               Guardar                                  #
    # =======================================================================
    def save_progress(self):
        if self.current_atajado is None:
            QMessageBox.warning(self, "Error", "Carga primero un atajado.")
            return

        today = QDate.currentDate().toString("yyyy-MM-dd")

        for r in range(self.table.rowCount()):
            iid = int(self.table.item(r, 0).text())
            pct = int(self.table.cellWidget(r, 9).currentText().replace("%", ""))

            chk = self.table.item(r, 5)
            inicio = self.table.cellWidget(r, 6)
            fin = self.table.cellWidget(r, 7)

            sd = inicio.date().toString("yyyy-MM-dd") if chk.checkState() == Qt.CheckState.Checked else None
            ed = fin.date().toString("yyyy-MM-dd") if chk.checkState() == Qt.CheckState.Checked else None

            existing = self.db.fetchall(
                "SELECT id FROM avances WHERE atajado_id=? AND item_id=?",
                (self.current_atajado, iid)
            )
            if existing:
                self.db.execute(
                    "UPDATE avances SET quantity=?, date=?, start_date=?, end_date=? "
                    "WHERE id=?",
                    (pct, today, sd, ed, existing[0][0])
                )
            else:
                self.db.execute(
                    "INSERT INTO avances(atajado_id,item_id,date,quantity,start_date,end_date) "
                    "VALUES(?,?,?,?,?,?)",
                    (self.current_atajado, iid, today, pct, sd, ed)
                )

        # Actualizar estado del atajado según avance ponderado por costo
        avg_row = self.db.fetchall(
            """
            SELECT SUM(i.total*i.incidence*a.quantity/100.0) / SUM(i.total*i.incidence)
            FROM avances a
            JOIN items i ON a.item_id = i.id
            WHERE a.atajado_id=? AND i.active=1
            """,
            (self.current_atajado,)
        )
        avg = (avg_row[0][0] or 0) * 100
        status = "Ejecutado" if avg == 100 else "En ejecución"

        self.db.execute(
            "UPDATE atajados SET status=? WHERE number=?",
            (status, self.current_atajado)
        )

        QMessageBox.information(self, "Guardado", "Avances registrados correctamente.")

        if self._save_callback:
            self._save_callback()
        else:
            wnd = self.window()
            if hasattr(wnd, "refresh_all"):
                wnd.refresh_all()

    # =======================================================================
    #                           Vista previa                                 #
    # =======================================================================
    def preview_image(self, item: QListWidgetItem):
        path = item.data(Qt.ItemDataRole.UserRole)
        paths = [
            self.img_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.img_list.count())
        ]
        dlg = ImagePreviewDialog(paths, paths.index(path))
        dlg.exec()
