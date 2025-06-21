# avance_tab.py  ·  Pestaña de registro de avances
# -------------------------------------------------
# • Divide sólo Cant. si Aplica = Sí
# • Autoajuste de columnas + scroll per-pixel
# • Splitter (miniaturas ⇆ vista previa)
# • Dropdown % avance, confirmaciones y notificaciones

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QSize, QDate
from PyQt6.QtGui import QPixmap, QIcon, QAction, QRegularExpressionValidator
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel, QComboBox, QCompleter,
    QTableWidget, QTableWidgetItem, QPushButton, QFileDialog, QMessageBox,
    QListWidget, QListWidgetItem, QDialog, QScrollArea, QHeaderView,
    QDateEdit, QLineEdit, QMenu
)

from database import Database, IMAGES_DIR


# ═══════════════════ Diálogo de vista previa en pantalla completa ══════════
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

        self.scroll = QScrollArea(widgetResizable=True)
        self.label = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.scroll.setWidget(self.label)
        lay.addWidget(self.scroll)
        self._load()

    def _step(self, d: int):
        self.idx = (self.idx + d) % len(self.paths)
        self._load()

    def resizeEvent(self, e):  # noqa
        super().resizeEvent(e)
        self._scale()

    def _load(self):
        self._pix = QPixmap(self.paths[self.idx])
        self._scale()

    def _scale(self):
        if not self._pix.isNull():
            s = self.scroll.viewport().size()
            self.label.setPixmap(self._pix.scaled(
                s, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            )


# ═══════════════════════════════════ AvanceTab ═════════════════════════════
class AvanceTab(QWidget):
    COL_ID, COL_NOM, COL_QTY, COL_PU, COL_TOT, COL_INI, COL_FIN, COL_COM, COL_PCT = range(9)

    # ------------------------------------------------------------------ #
    def __init__(self, db: Database, save_callback=None):
        super().__init__()
        self.db = db
        self._save_cb = save_callback
        self.current_atajado: int | None = None

        # Tipografía uniforme + campos inválidos en rojo
        self.setStyleSheet("""
            QWidget { font-family:'Segoe UI', sans-serif; font-size:10.5pt; }
            QLineEdit:invalid { border:1px solid red; }
        """)

        root = QVBoxLayout(self)

        # ───────────── Selector superior ─────────────
        sel = QHBoxLayout()
        sel.addWidget(QLabel("Atajado / Beneficiario:"))
        self.at_combo = QComboBox(editable=True)
        self.refresh_btn = QPushButton(QIcon.fromTheme("view-refresh"), "")
        self.refresh_btn.clicked.connect(self._populate_selector)
        sel.addWidget(self.at_combo, 1)
        sel.addWidget(self.refresh_btn)
        root.addLayout(sel)

        # ───────────── Info atajado destacada ─────────────
        self.info_lbl = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.info_lbl.setStyleSheet("""
            QLabel {
                background:#0e639c; color:white; padding:6px 4px; border-radius:6px;
                font-weight:600;
            }""")
        root.addWidget(self.info_lbl)

        # ───────────── Tabla de ítems ─────────────
        self.table = QTableWidget()
        self.table.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hdr.setStretchLastSection(True)
        root.addWidget(self.table, 1)

        btn_bar = QHBoxLayout()
        self.save_btn = QPushButton(QIcon.fromTheme("document-save"), "Guardar avance")
        self.save_btn.clicked.connect(self.save_progress)
        btn_bar.addStretch(); btn_bar.addWidget(self.save_btn)
        root.addLayout(btn_bar)

        # ───────────── Panel inferior de imágenes ─────────────
        img_split = QSplitter(Qt.Orientation.Horizontal)
        img_split.setFixedHeight(250)
        root.addWidget(img_split)

        left = QWidget(); l_lay = QVBoxLayout(left); img_split.addWidget(left)
        self.img_list = QListWidget(viewMode=QListWidget.ViewMode.IconMode)
        self.img_list.setIconSize(QSize(100, 100))
        self.img_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.img_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.img_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.img_list.itemClicked.connect(self._show_preview)
        self.img_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.img_list.customContextMenuRequested.connect(self._thumb_menu)
        l_lay.addWidget(self.img_list)

        self.img_btn = QPushButton(QIcon.fromTheme("list-add"), "Añadir imágenes")
        self.img_btn.clicked.connect(self._select_images)
        l_lay.addWidget(self.img_btn)

        right = QWidget(); r_lay = QVBoxLayout(right); img_split.addWidget(right)

        self.big_preview = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.big_preview.setStyleSheet("border:1px solid #aaa;")
        r_lay.addWidget(self.big_preview)
        # Inicial
        self._populate_selector()
        self.at_combo.currentTextChanged.connect(self.load_items)

    # ==================== Selector ====================
    def _populate_selector(self):
        self.at_combo.blockSignals(True)
        opts = [
            f"{num} – {ben}"
            for num, ben in self.db.fetchall(
                "SELECT number, beneficiario FROM atajados ORDER BY number"
            )
        ]
        self.at_combo.clear()
        self.at_combo.addItems(opts)
        self.at_combo.setCompleter(
            QCompleter(opts, caseSensitivity=Qt.CaseSensitivity.CaseInsensitive)
        )
        self.at_combo.blockSignals(False)
        if opts:
            self.at_combo.setCurrentIndex(0)
            self.load_items()

    # ==================== Carga tabla ====================
    def load_items(self):
        txt = self.at_combo.currentText().strip()
        m = re.match(r"^(\d+)", txt)
        if not m:
            self._clear_ui()
            return
        self.current_atajado = int(m.group(1))

        # Info encabezado
        info = self.db.fetchone(
            "SELECT comunidad, beneficiario, ci, este, norte "
            "FROM atajados WHERE number=?", (self.current_atajado,)
        )
        if info:
            com, ben, ci, este, norte = info
            self.info_lbl.setText(
                f"Comunidad: <b>{com}</b>   &nbsp;|&nbsp;   "
                f"Beneficiario: <b>{ben}</b>   &nbsp;|&nbsp;   "
                f"CI: {ci}   &nbsp;|&nbsp;   Coord: Este {este or '—'}, Norte {norte or '—'}"
            )
        else:
            self.info_lbl.clear()

        # Datos de ítems
        rows = self.db.fetchall(
            "SELECT id, name, total, incidence FROM items WHERE active=1 ORDER BY id"
        )
        if not rows:
            self._clear_ui(); return

        n_ata = self.db.fetchone("SELECT COUNT(*) FROM atajados")[0] or 1

        hdrs = ["ID", "Nombre", "Cant.", "P.U.", "Total",
                "Inicio", "Fin", "Comentario", "Avance (%)"]
        self.table.blockSignals(True)
        self.table.setRowCount(len(rows)); self.table.setColumnCount(len(hdrs))
        self.table.setHorizontalHeaderLabels(hdrs)

        for r, (iid, nom, qty_tot, pu) in enumerate(rows):
            qty = round(qty_tot / n_ata, 3)
            total = round(qty * pu, 2)
            for c, v in enumerate((iid, nom, f"{qty:g}", f"{pu:.2f}", f"{total:.2f}")):
                it = QTableWidgetItem(str(v))
                it.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                self.table.setItem(r, c, it)

            ini = QDateEdit(calendarPopup=True); ini.setDate(QDate.currentDate())
            fin = QDateEdit(calendarPopup=True); fin.setDate(QDate.currentDate())
            com = QLineEdit()
            pct = QComboBox(); pct.addItems(["0 %", "25 %", "50 %", "75 %", "100 %"])

            self.table.setCellWidget(r, self.COL_INI, ini)
            self.table.setCellWidget(r, self.COL_FIN, fin)
            self.table.setCellWidget(r, self.COL_COM, com)
            self.table.setCellWidget(r, self.COL_PCT, pct)

            old = self.db.fetchone(
                "SELECT quantity, start_date, end_date, comment "
                "FROM avances WHERE atajado_id=? AND item_id=?",
                (self.current_atajado, iid)
            )
            if old:
                q, sd, ed, com_old = old
                pct.setCurrentText(f"{int(q)} %")
                if sd: ini.setDate(QDate.fromString(sd, "yyyy-MM-dd"))
                if ed: fin.setDate(QDate.fromString(ed, "yyyy-MM-dd"))
                if com_old: com.setText(com_old)

        self.table.blockSignals(False)
        self.table.resizeRowsToContents()
        self._reload_thumbs()
        self.img_btn.setEnabled(True); self.save_btn.setEnabled(True)

    # ==================== Imágenes ====================
    def _select_images(self):
        if self.current_atajado is None:
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Seleccionar imágenes", "", "Imágenes (*.png *.jpg *.jpeg *.bmp)"
        )
        if paths:
            dest = IMAGES_DIR / str(self.current_atajado)
            dest.mkdir(parents=True, exist_ok=True)
            for src in paths:
                shutil.copy(src, dest / Path(src).name)
            self._reload_thumbs()
            QMessageBox.information(self, "Imágenes", "Imágenes añadidas correctamente.")

    def _reload_thumbs(self):
        self.img_list.clear(); self.big_preview.clear()
        if self.current_atajado is None:
            return
        d = IMAGES_DIR / str(self.current_atajado)
        if not d.exists():
            return
        for p in sorted(d.glob("*.[pj][pn]g")) + sorted(d.glob("*.bmp")):
            icon = QPixmap(str(p)).scaled(100, 100, Qt.AspectRatioMode.KeepAspectRatio,
                                          Qt.TransformationMode.SmoothTransformation)
            it = QListWidgetItem(QIcon(icon), ""); it.setData(Qt.ItemDataRole.UserRole, str(p))
            self.img_list.addItem(it)

    def _show_preview(self, item: QListWidgetItem):
        path = item.data(Qt.ItemDataRole.UserRole)
        pix = QPixmap(path).scaled(
            self.big_preview.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.big_preview.setPixmap(pix)

    def _thumb_menu(self, pos):
        it = self.img_list.itemAt(pos)
        if not it:
            return
        if QMessageBox.question(
            self, "Eliminar imagen", "¿Eliminar esta imagen?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            p = Path(it.data(Qt.ItemDataRole.UserRole))
            p.unlink(missing_ok=True)
            self.img_list.takeItem(self.img_list.row(it))
            self.big_preview.clear()
            QMessageBox.information(self, "Imágenes", "Imagen eliminada.")

    # ==================== Guardar ====================
    def save_progress(self):
        if self.current_atajado is None:
            self._notify("Selecciona un atajado antes de guardar.", "warning"); return

        today = QDate.currentDate().toString("yyyy-MM-dd")
        filas_ok, errores = 0, []

        cur = self.db.conn.cursor()
        try:
            for r in range(self.table.rowCount()):
                id_item = self.table.item(r, self.COL_ID)
                if not id_item:
                    continue
                try:
                    iid = int(id_item.text())
                    pct = int(self.table.cellWidget(r, self.COL_PCT).currentText().rstrip(" %"))
                    ini = self.table.cellWidget(r, self.COL_INI).date().toString("yyyy-MM-dd")
                    fin = self.table.cellWidget(r, self.COL_FIN).date().toString("yyyy-MM-dd")
                    com = self.table.cellWidget(r, self.COL_COM).text()
                    cur.execute(
                        """
                        INSERT INTO avances(atajado_id, item_id, date,
                                            quantity, start_date, end_date, comment)
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
            self.db.conn.commit()
        finally:
            cur.close()

        if filas_ok == 0:
            self._notify("No se pudo guardar ningún avance.\n" + "\n".join(errores), "error"); return

        self._recalcular_estado()
        if errores:
            self._notify("Avance guardado con advertencias:\n" + "\n".join(errores), "warning")
        else:
            self._notify("Avances registrados correctamente.", "info")
        if self._save_cb:
            self._save_cb()

    # ==================== Recalcular % global ====================
    def _recalcular_estado(self):
        n_ata = self.db.fetchone("SELECT COUNT(*) FROM atajados")[0] or 1
        rows = self.db.fetchall(
            """
            SELECT i.total, i.incidence,
                   COALESCE(a.quantity, 0)
            FROM items i
            LEFT JOIN avances a
              ON a.item_id = i.id AND a.atajado_id = ?
            WHERE i.active = 1
            """, (self.current_atajado,)
        )
        total_val = ejec_val = 0.0
        for qty_tot, pu, pct in rows:
            qty = qty_tot / n_ata
            val = qty * pu
            total_val += val; ejec_val += val * pct / 100.0

        avg_pct = round(ejec_val / total_val * 100, 1) if total_val else 0
        estado = "Ejecutado" if avg_pct >= 100 else "En ejecución"
        self.db.execute(
            "UPDATE atajados SET porcentaje=?, status=? WHERE number=?",
            (avg_pct, estado, self.current_atajado)
        )

    # ==================== Utils ====================
    def _clear_ui(self):
        self.info_lbl.clear(); self.table.setRowCount(0)
        self.img_list.clear(); self.big_preview.clear()
        self.img_btn.setEnabled(False); self.save_btn.setEnabled(False)

    def _notify(self, msg: str, kind: str = "info"):
        {"info": QMessageBox.information,
         "warning": QMessageBox.warning,
         "error": QMessageBox.critical}.get(kind, QMessageBox.information)(
             self, "Seguimiento de Avances", msg)
