"""
File System Module
A real file manager that browses the actual host filesystem.
Supports create / delete / rename files and folders, and opens text files.

FIX: Removed duplicate imports and unused QSortFilterProxyModel import.
"""

import os
import shutil
import subprocess
import platform
from pathlib import Path

from PyQt6.QtCore import Qt, QDir, QDateTime, QModelIndex, QSize
from PyQt6.QtGui import QFileSystemModel
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeView, QListView,
    QSplitter, QPushButton, QLineEdit, QLabel, QMessageBox,
    QInputDialog, QMenu, QDialog, QTextEdit, QDialogButtonBox,
    QToolBar, QSizePolicy, QFileDialog,
)

FS_STYLE = """
QWidget { background: #161b22; color: #c9d1d9; }
QTreeView, QListView {
    background: #0d1117;
    color: #c9d1d9;
    border: 1px solid #30363d;
    alternate-background-color: #161b22;
    font-size: 13px;
}
QTreeView::item:selected, QListView::item:selected {
    background: #1f6feb;
    color: #ffffff;
}
QLineEdit {
    background: #21262d;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 13px;
}
QPushButton {
    background: #21262d;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 4px;
    padding: 4px 12px;
    font-size: 12px;
}
QPushButton:hover { background: #30363d; }
QToolBar { background: #161b22; border: none; spacing: 4px; padding: 4px; }
QHeaderView::section {
    background: #21262d;
    color: #8b949e;
    border: none;
    padding: 4px;
    font-size: 12px;
}
"""

TEXT_EXTENSIONS = {
    ".txt", ".md", ".py", ".js", ".ts", ".json", ".yaml", ".yml",
    ".csv", ".html", ".css", ".sh", ".bat", ".ini", ".cfg", ".log",
    ".xml", ".toml", ".env", ".gitignore",
}


class TextEditorDialog(QDialog):
    def __init__(self, path: str, read_only: bool = False, parent=None):
        super().__init__(parent)
        self._path = path
        self.setWindowTitle(os.path.basename(path))
        self.resize(700, 500)

        layout = QVBoxLayout(self)
        self._editor = QTextEdit()
        self._editor.setReadOnly(read_only)
        self._editor.setStyleSheet(
            "background:#0d1117; color:#c9d1d9;"
            "font-family:'Consolas','Courier New',monospace; font-size:13px;"
        )
        try:
            with open(path, "r", errors="replace") as f:
                self._editor.setPlainText(f.read())
        except Exception as e:
            self._editor.setPlainText(f"[Error reading file: {e}]")

        layout.addWidget(self._editor)

        btns = QDialogButtonBox()
        if not read_only:
            save_btn = btns.addButton("Save", QDialogButtonBox.ButtonRole.AcceptRole)
            save_btn.clicked.connect(self._save)
        close_btn = btns.addButton("Close", QDialogButtonBox.ButtonRole.RejectRole)
        close_btn.clicked.connect(self.reject)
        layout.addWidget(btns)

    def _save(self):
        try:
            with open(self._path, "w") as f:
                f.write(self._editor.toPlainText())
            QMessageBox.information(self, "Saved", "File saved successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


class FileManagerWidget(QWidget):
    def __init__(self, start_dir: str = "", parent=None):
        super().__init__(parent)
        self._cwd = start_dir or os.path.expanduser("~")
        self._history: list[str] = []
        self.setStyleSheet(FS_STYLE)
        self._build_ui()
        self._navigate(self._cwd)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        toolbar = QHBoxLayout()

        self._back_btn = QPushButton("← Back")
        self._back_btn.setFixedWidth(70)
        self._back_btn.clicked.connect(self._go_back)
        toolbar.addWidget(self._back_btn)

        self._up_btn = QPushButton("↑ Up")
        self._up_btn.setFixedWidth(60)
        self._up_btn.clicked.connect(self._go_up)
        toolbar.addWidget(self._up_btn)

        self._path_bar = QLineEdit()
        self._path_bar.returnPressed.connect(
            lambda: self._navigate(self._path_bar.text())
        )
        toolbar.addWidget(self._path_bar, 1)

        new_folder_btn = QPushButton("+ Folder")
        new_folder_btn.clicked.connect(self._new_folder)
        toolbar.addWidget(new_folder_btn)

        new_file_btn = QPushButton("+ File")
        new_file_btn.clicked.connect(self._new_file)
        toolbar.addWidget(new_file_btn)

        layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._tree_model = QFileSystemModel()
        self._tree_model.setRootPath(QDir.rootPath())
        self._tree_model.setFilter(QDir.Filter.AllDirs | QDir.Filter.NoDotAndDotDot)

        self._tree = QTreeView()
        self._tree.setModel(self._tree_model)
        for col in range(1, 4):
            self._tree.hideColumn(col)
        self._tree.clicked.connect(self._on_tree_click)
        splitter.addWidget(self._tree)

        self._list_model = QFileSystemModel()
        self._list_model.setRootPath(self._cwd)

        self._list = QListView()
        self._list.setModel(self._list_model)
        self._list.setViewMode(QListView.ViewMode.IconMode)
        self._list.setIconSize(QSize(48, 48))
        self._list.setGridSize(QSize(90, 90))
        self._list.setWordWrap(True)
        self._list.setResizeMode(QListView.ResizeMode.Adjust)
        self._list.setUniformItemSizes(True)
        self._list.setSpacing(4)
        self._list.doubleClicked.connect(self._on_list_double_click)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._show_context_menu)
        splitter.addWidget(self._list)

        splitter.setSizes([220, 680])
        layout.addWidget(splitter, 1)   # stretch=1 → fills all remaining height

        self._status = QLabel()
        self._status.setFixedHeight(24)
        self._status.setStyleSheet("color:#8b949e; font-size:11px; padding-left:6px;")
        layout.addWidget(self._status)

    def _navigate(self, path: str):
        path = os.path.abspath(path)
        if not os.path.isdir(path):
            return
        self._history.append(self._cwd)
        self._cwd = path
        self._path_bar.setText(path)
        root = self._list_model.setRootPath(path)
        self._list.setRootIndex(root)
        tree_idx = self._tree_model.index(path)
        self._tree.setCurrentIndex(tree_idx)
        self._tree.scrollTo(tree_idx)
        self._update_status()

    def _go_back(self):
        if self._history:
            path = self._history.pop()
            self._cwd = path
            self._path_bar.setText(path)
            root = self._list_model.setRootPath(path)
            self._list.setRootIndex(root)
            self._update_status()

    def _go_up(self):
        parent = str(Path(self._cwd).parent)
        if parent != self._cwd:
            self._navigate(parent)

    def _on_tree_click(self, idx: QModelIndex):
        path = self._tree_model.filePath(idx)
        if os.path.isdir(path):
            self._navigate(path)

    def _on_list_double_click(self, idx: QModelIndex):
        path = self._list_model.filePath(idx)
        if os.path.isdir(path):
            self._navigate(path)
        elif os.path.isfile(path):
            self._open_file(path)

    def _new_folder(self):
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if ok and name:
            try:
                os.makedirs(os.path.join(self._cwd, name), exist_ok=True)
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def _new_file(self):
        name, ok = QInputDialog.getText(self, "New File", "File name:")
        if ok and name:
            path = os.path.join(self._cwd, name)
            try:
                open(path, "a").close()
                self._open_file(path)
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def _open_file(self, path: str):
        ext = Path(path).suffix.lower()
        if ext in TEXT_EXTENSIONS or os.path.getsize(path) < 500_000:
            dlg = TextEditorDialog(path, parent=self)
            dlg.exec()
        else:
            try:
                if platform.system() == "Darwin":
                    subprocess.Popen(["open", path])
                elif platform.system() == "Windows":
                    os.startfile(path)
                else:
                    subprocess.Popen(["xdg-open", path])
            except Exception as e:
                QMessageBox.warning(self, "Cannot open", str(e))

    def _show_context_menu(self, pos):
        idx = self._list.indexAt(pos)
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background:#21262d; color:#c9d1d9; border:1px solid #30363d; }"
            "QMenu::item:selected { background:#1f6feb; }"
        )

        if idx.isValid():
            path = self._list_model.filePath(idx)
            is_dir = os.path.isdir(path)

            open_action = menu.addAction("Open")
            open_action.triggered.connect(
                lambda: self._navigate(path) if is_dir else self._open_file(path)
            )

            rename_action = menu.addAction("Rename")
            rename_action.triggered.connect(lambda: self._rename(path))

            delete_action = menu.addAction("Delete")
            delete_action.triggered.connect(lambda: self._delete(path))

            menu.addSeparator()

        new_folder_act = menu.addAction("New Folder")
        new_folder_act.triggered.connect(self._new_folder)

        new_file_act = menu.addAction("New File")
        new_file_act.triggered.connect(self._new_file)

        menu.exec(self._list.mapToGlobal(pos))

    def _rename(self, path: str):
        old_name = os.path.basename(path)
        new_name, ok = QInputDialog.getText(
            self, "Rename", "New name:", text=old_name
        )
        if ok and new_name and new_name != old_name:
            new_path = os.path.join(os.path.dirname(path), new_name)
            try:
                os.rename(path, new_path)
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def _delete(self, path: str):
        name = os.path.basename(path)
        reply = QMessageBox.question(
            self, "Delete", f"Delete '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def _update_status(self):
        try:
            entries = os.listdir(self._cwd)
            files = sum(1 for e in entries if os.path.isfile(os.path.join(self._cwd, e)))
            folders = sum(1 for e in entries if os.path.isdir(os.path.join(self._cwd, e)))
            self._status.setText(f"{folders} folder(s), {files} file(s) — {self._cwd}")
        except Exception:
            self._status.setText(self._cwd)
