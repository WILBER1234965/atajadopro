"""
tabs/avance_tab.py
Pestaña profesional de registro de avances
------------------------------------------
• Carga todos los ítems activos        • Guarda con UPSERT
• Selector con autocompletado          • Miniaturas con menú contextual
• Vista previa a pantalla completa     • Mensajes uniformes (info/warn/error)
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
import re

from PyQt6.QtCore import Qt, QSize, QDate
from PyQt6.QtGui import QPixmap, QIcon, QAction
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QCompleter,
    QTableWidget, QTableWidgetItem, QPushButton, QFileDialog, QMessageBox,
    QListWidget, QListWidgetItem, QDialog, QScrollArea, QHeaderView,
    QDateEdit, QLineEdit, QMenu
)

from database import Database, IMAGES_DIR


# ═════════════════════════════════ Vista previa ═════════════════════════════ #
class ImagePreviewDialog(QDialog):
    def __init__(self, paths: list[str], idx: int = 0):
        super().__init__()
        self.paths, self.idx = paths, idx
        self.setWindowState(Qt.WindowState.WindowMaximized)
        self.setWindowTitle("Vista previa")

        lay = QVBoxLayout(self)
        nav = QHBoxLayout()
        nav.addWidget(QPushButton("◀", clicked=lambda: self._step(-1)))
        nav.addStretch()
        nav.addWidget(QPushButton("▶", clicked=lambda: self._step(+1)))
        lay.addLayout(nav)

        self.scr = QScrollArea(widgetResizable=True)
        self.lbl = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.scr.setWidget(self.lbl)
        lay.addWidget(self.scr)

        self._load()

    # ---------------- helpers ----------------
    def _step(self, d: int):
        self.idx = (self.idx + d) % len(self.paths)
        self._load()

    def resizeEvent(self, e):                                                  # noqa
        super().resizeEvent(e)
        self._scale()

    def _load(self):
        self._pix = QPixmap(self.paths[self.idx])
        self._scale()

    def _scale(self):
        if self._pix.isNull():
            return
        s = self.scr.viewport().size()
        self.lbl.setPixmap(
            self._pix.scaled(
                s, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
        )


# ═══════════════════════════════════ AvanceTab ══════════════════════════════ #
class AvanceTab(QWidget):
    COL_ID, COL_NOM, COL_QTY, COL_PU, COL_TOT, COL_INI, COL_FIN, COL_COM, COL_PCT = range(9)

    def __init__(self, db: Database, save_callback=None):
        super().__init__()
        self.db = db
        self._save_cb = save_callback
        self.current_atajado: int | None = None

        root = QVBoxLayout(self)

        # ────────── Selector ──────────
        sel = QHBoxLayout()
        sel.addWidget(QLabel("Atajado / Beneficiario:"))
        self.at_combo = QComboBox(editable=True)
        self.refresh_btn = QPushButton("⟳", clicked=self._populate_selector)
        sel.addWidget(self.at_combo, 1)
        sel.addWidget(self.refresh_btn)
        root.addLayout(sel)

        # ────────── Info beneficiario ──────────
        self.info_lbl = QLabel()
        self.info_lbl.setStyleSheet("font-weight:600; color:#d0d0d0;")
        root.addWidget(self.info_lbl)

        # ────────── Tabla de ítems ──────────
        self.table = QTableWidget()
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)
        root.addWidget(self.table)

        # ────────── Acciones ──────────
        act = QHBoxLayout()
        self.img_btn = QPushButton("📎 Adjuntar imágenes", clicked=self.attach_images)
        self.save_btn = QPushButton("💾 Guardar avance", clicked=self.save_progress)
        act.addWidget(self.img_btn)
        act.addWidget(self.save_btn)
        act.addStretch()
        root.addLayout(act)

        # ────────── Miniaturas ──────────
        self.img_list = QListWidget(viewMode=QListWidget.ViewMode.IconMode)
        self.img_list.setIconSize(QSize(100, 100))
        self.img_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.img_list.itemDoubleClicked.connect(self._preview)
        self.img_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.img_list.customContextMenuRequested.connect(self._thumb_menu)
        root.addWidget(self.img_list)

        # Cargar selector
        self._populate_selector()
        self.at_combo.currentTextChanged.connect(self.load_items)
        

    # ===================================================================== #
    #                              Selector                                 #
    # ===================================================================== #
    def _populate_selector(self):
        self.at_combo.blockSignals(True)
        opts = [f"{n} – {b}" for n, b in
                self.db.fetchall("SELECT number, beneficiario FROM atajados ORDER BY number")]
        self.at_combo.clear()
        self.at_combo.addItems(opts)
        self.at_combo.setCompleter(QCompleter(opts, caseSensitivity=Qt.CaseSensitivity.CaseInsensitive))
        self.at_combo.blockSignals(False)

        if opts:
            self.at_combo.setCurrentIndex(0)
            self.load_items()

    # ===================================================================== #
    #                       Información + Carga tabla                       #
    # ===================================================================== #
    def load_items(self):
        txt = self.at_combo.currentText().strip()
        if not txt:
            self._clear_ui()
            return
        match = re.match(r"(\d+)", txt)
        if not match:
            self._clear_ui()
            return
        self.current_atajado = int(match.group(1))
        self._set_info()
        rows = self.db.fetchall(
            "SELECT id, name, total, COALESCE(unit_price, incidence, 0) "
            "FROM items WHERE active=1 OR lower(CAST(active AS TEXT)) IN ('si','sí')"
        )
        if not rows:
            self._clear_ui()
            return

        headers = ["ID", "Nombre", "Cant.", "P.U.", "Total",
                   "Inicio", "Fin", "Comentario", "Avance (%)"]
        n_ata = self.db.fetchone("SELECT COUNT(*) FROM atajados")[0] or 1

        self.table.blockSignals(True)
        self.table.setRowCount(len(rows))
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        for r, (iid, nombre, qty_tot, pu) in enumerate(rows):
            qty = qty_tot / n_ata
            total = qty * pu
            for c, val in enumerate((iid, nombre, f"{qty:.2f}", pu, f"{total:.2f}")):
                item = QTableWidgetItem(str(val))
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self.table.setItem(r, c, item)

            ini = QDateEdit(calendarPopup=True); ini.setDate(QDate.currentDate())
            fin = QDateEdit(calendarPopup=True); fin.setDate(QDate.currentDate())
            self.table.setCellWidget(r, self.COL_INI, ini)
            self.table.setCellWidget(r, self.COL_FIN, fin)
            self.table.setCellWidget(r, self.COL_COM, QLineEdit())

            pct = QComboBox(); pct.addItems([f"{p}%" for p in (0, 25, 50, 75, 100)])
            self.table.setCellWidget(r, self.COL_PCT, pct)

            # Cargar avance previo
            old = self.db.fetchone(
                "SELECT quantity,start_date,end_date,comment "
                "FROM avances WHERE atajado_id=? AND item_id=?",
                (self.current_atajado, iid)
            )
            if old:
                q, sd, ed, com = old
                pct.setCurrentText(f"{int(q)}%")
                if sd: ini.setDate(QDate.fromString(sd, "yyyy-MM-dd"))
                if ed: fin.setDate(QDate.fromString(ed, "yyyy-MM-dd"))
                if com: self.table.cellWidget(r, self.COL_COM).setText(com)

        self.table.blockSignals(False)
        self.table.resizeRowsToContents()
        self._reload_thumbs()
        self.img_btn.setEnabled(True)
        self.save_btn.setEnabled(True)

    def _set_info(self):
        info = self.db.fetchone(
            "SELECT comunidad, beneficiario, ci, este, norte "
            "FROM atajados WHERE number=?", (self.current_atajado,)
        )
        if not info:
            self.info_lbl.clear()
            return
        com, ben, ci, e, n = info
        self.info_lbl.setText(
            f"Comunidad: <b>{com}</b> – Beneficiario: <b>{ben}</b> – "
            f"CI: {ci} – Coord: Este {e or '—'}, Norte {n or '—'}"
        )

    def _clear_ui(self):
        self.info_lbl.clear()
        self.table.setRowCount(0)
        self.img_list.clear()
        self.img_btn.setEnabled(False)
        self.save_btn.setEnabled(False)

    # ===================================================================== #
    #                               Imágenes                                #
    # ===================================================================== #
    def attach_images(self):
        if self.current_atajado is None:
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Seleccionar imágenes", "", "Imágenes (*.png *.jpg *.jpeg *.bmp)"
        )
        if not paths:
            return
        dest = IMAGES_DIR / str(self.current_atajado)
        dest.mkdir(parents=True, exist_ok=True)
        for src in paths:
            name = f"{datetime.now().timestamp():.6f}_{Path(src).name}"
            shutil.copy(src, dest / name)
        self._reload_thumbs()

    def _reload_thumbs(self):
        self.img_list.clear()
        if self.current_atajado is None:
            return
        dir_ = IMAGES_DIR / str(self.current_atajado)
        if not dir_.exists():
            return
        for p in sorted(dir_.glob("*.[pj][pn]g")) + sorted(dir_.glob("*.bmp")):
            icon = QPixmap(str(p)).scaled(
                100, 100, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            it = QListWidgetItem(QIcon(icon), "")
            it.setData(Qt.ItemDataRole.UserRole, str(p))
            self.img_list.addItem(it)

    def _preview(self, item: QListWidgetItem):
        paths = [self.img_list.item(i).data(Qt.ItemDataRole.UserRole)
                 for i in range(self.img_list.count())]
        ImagePreviewDialog(paths, paths.index(item.data(Qt.ItemDataRole.UserRole))).exec()

    def _thumb_menu(self, pos):
        item = self.img_list.itemAt(pos)
        if not item:
            return
        m = QMenu(self)
        act_del = QAction("Eliminar", self)
        m.addAction(act_del)
        if m.exec(self.img_list.mapToGlobal(pos)) == act_del:
            path = Path(item.data(Qt.ItemDataRole.UserRole))
            try:
                path.unlink(missing_ok=True)
                self.img_list.takeItem(self.img_list.row(item))
            except Exception as e:
                self._notify(f"No se pudo eliminar {path.name}: {e}", "warning")

    # ===================================================================== #
    #                                 Guardar                               #
    # ===================================================================== #
    def save_progress(self):
        if self.current_atajado is None:
            self._notify("Selecciona un atajado antes de guardar.", "warning")
            return

        today = QDate.currentDate().toString("yyyy-MM-dd")
        filas_ok, errores = 0, []

        for r in range(self.table.rowCount()):
            cell_id = self.table.item(r, self.COL_ID)
            if cell_id is None:
                continue  # fila vacía

            try:
                iid = int(cell_id.text())
                pct = int(self.table.cellWidget(r, self.COL_PCT).currentText()[:-1])
                ini = self.table.cellWidget(r, self.COL_INI).date().toString("yyyy-MM-dd")
                fin = self.table.cellWidget(r, self.COL_FIN).date().toString("yyyy-MM-dd")
                com = self.table.cellWidget(r, self.COL_COM).text()

                self.db.execute(
                    """
                    INSERT INTO avances(atajado_id,item_id,date,quantity,start_date,end_date,comment)
                    VALUES(?,?,?,?,?,?,?)
                    ON CONFLICT(atajado_id,item_id) DO UPDATE SET
                        date=excluded.date, quantity=excluded.quantity,
                        start_date=excluded.start_date, end_date=excluded.end_date,
                        comment=excluded.comment
                    """,
                    (self.current_atajado, iid, today, pct, ini, fin, com)
                )
                filas_ok += 1

            except Exception as e:
                errores.append(f"Fila {r+1}: {e}")

        if filas_ok == 0:
            self._notify("No se pudo guardar ningún avance.\n" + "\n".join(errores), "error")
            return

        self._recalcular_estado()

        if errores:
            self._notify("Avance guardado con advertencias:\n" + "\n".join(errores), "warning")
        else:
            self._notify("Avances registrados correctamente.", "info")

        if self._save_cb:
            self._save_cb()

    def _recalcular_estado(self):
        avg = self.db.fetchone(
            """
            SELECT COALESCE(SUM(i.total*COALESCE(i.unit_price,i.incidence,0)*a.quantity/100.0) /
                   SUM(i.total*COALESCE(i.unit_price,i.incidence,0)), 0)
            FROM avances a JOIN items i ON a.item_id=i.id
            WHERE a.atajado_id=? AND (i.active=1 OR lower(CAST(i.active AS TEXT)) IN ('si','sí'))
            """, (self.current_atajado,)
        )[0] * 100
        estado = "Ejecutado" if avg == 100 else "En ejecución"
        self.db.execute("UPDATE atajados SET status=? WHERE number=?",
                        (estado, self.current_atajado))

    # ===================================================================== #
    #                                   Utils                               #
    # ===================================================================== #
    def _notify(self, msg: str, kind: str = "info"):
        {"info": QMessageBox.information,
         "warning": QMessageBox.warning,
         "error": QMessageBox.critical}.get(kind, QMessageBox.information)(
             self, "Seguimiento de Avances", msg)
