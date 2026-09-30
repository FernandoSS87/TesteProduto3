#!/usr/bin/env python3
"""Interface gráfica (PySide6) do gitbuild."""
import os
import sys

from PySide6.QtCore import QObject, QSettings, QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QSplitter,
    QVBoxLayout, QWidget,
)

import gitbuild


class BuildWorker(QObject):
    """Roda o plano numa thread separada, emitindo a saída linha a linha."""
    line = Signal(str)
    step = Signal(str, str)
    finished = Signal(list)

    def __init__(self, steps, repo):
        super().__init__()
        self.steps, self.repo = steps, repo

    def run(self):
        results = gitbuild.run_plan(
            self.steps, cwd=self.repo,
            on_line=self.line.emit, on_step=self.step.emit,
        )
        self.finished.emit(results)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GitBuild")
        self.resize(1000, 650)
        self.settings = QSettings("GitBuild", "GitBuild")
        self.steps = []
        self.thread = None

        self.repo_edit = QLineEdit(self.settings.value("repo", "", str))
        browse = QPushButton("Escolher pasta…")
        browse.clicked.connect(self.choose_repo)
        self.base_edit = QLineEdit()
        self.base_edit.setPlaceholderText("Branch/ref base (vazio = alterações locais)")
        refresh = QPushButton("Atualizar")
        refresh.clicked.connect(self.refresh)
        self.build_btn = QPushButton("Compilar")
        self.build_btn.clicked.connect(self.build)

        top = QHBoxLayout()
        top.addWidget(QLabel("Repositório:"))
        top.addWidget(self.repo_edit, 1)
        top.addWidget(browse)
        opts = QHBoxLayout()
        opts.addWidget(QLabel("Base:"))
        opts.addWidget(self.base_edit, 1)
        opts.addWidget(refresh)
        opts.addWidget(self.build_btn)

        self.files_list = QListWidget()
        self.steps_list = QListWidget()
        self.log = QPlainTextEdit(readOnly=True)
        self.log.setMaximumBlockCount(10000)

        lists = QSplitter()
        for title, widget in (("Arquivos alterados", self.files_list), ("Comandos a executar", self.steps_list)):
            box = QWidget()
            lay = QVBoxLayout(box)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(QLabel(title))
            lay.addWidget(widget)
            lists.addWidget(box)
        main = QSplitter()
        main.setOrientation(main.orientation().Vertical)
        main.addWidget(lists)
        main.addWidget(self.log)
        main.setSizes([300, 300])

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.addLayout(top)
        lay.addLayout(opts)
        lay.addWidget(main, 1)
        self.setCentralWidget(central)
        self.statusBar().showMessage("Pronto")

        if self.repo_edit.text():
            self.refresh()

    # -- ações ---------------------------------------------------------
    def choose_repo(self):
        path = QFileDialog.getExistingDirectory(self, "Escolher repositório", self.repo_edit.text())
        if path:
            self.repo_edit.setText(path)
            self.settings.setValue("repo", path)
            self.refresh()

    def refresh(self):
        repo = self.repo_edit.text().strip()
        self.files_list.clear()
        self.steps_list.clear()
        self.steps = []
        self.build_btn.setEnabled(False)
        if not os.path.isdir(repo):
            self.statusBar().showMessage("Selecione uma pasta de repositório válida")
            return
        try:
            config = gitbuild.load_config(os.path.join(repo, gitbuild.DEFAULT_CONFIG))
            files = gitbuild.changed_files(self.base_edit.text().strip() or None, repo=repo)
        except (OSError, ValueError, RuntimeError) as exc:
            self.statusBar().showMessage(f"Erro: {exc}")
            return
        self.steps = gitbuild.plan(config, files)
        self.files_list.addItems(files)
        self.steps_list.addItems(f"[{n}] {c}" for n, c in self.steps)
        self.build_btn.setEnabled(bool(self.steps))
        self.statusBar().showMessage(f"{len(files)} arquivo(s) alterado(s), {len(self.steps)} comando(s)")

    def build(self):
        if self.thread:
            return
        self.log.clear()
        self.build_btn.setEnabled(False)
        self.thread = QThread(self)
        self.worker = BuildWorker(self.steps, self.repo_edit.text().strip())
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.line.connect(self.log.appendPlainText)
        self.worker.step.connect(lambda n, c: self.log.appendPlainText(f"\n[{n}] $ {c}"))
        self.worker.finished.connect(self.on_finished)
        self.statusBar().showMessage("Compilando…")
        self.thread.start()

    def on_finished(self, results):
        self.thread.quit()
        self.thread.wait()
        self.thread = None
        failed = [r for r in results if r["returncode"] != 0]
        if failed:
            self.log.appendPlainText(f"\nFALHOU: {failed[0]['name']} (código {failed[0]['returncode']})")
            self.statusBar().showMessage("Build falhou")
        else:
            self.log.appendPlainText("\nBuild concluído.")
            self.statusBar().showMessage("Build concluído")
        self.build_btn.setEnabled(bool(self.steps))

    def closeEvent(self, event):
        if self.thread:
            QMessageBox.warning(self, "GitBuild", "Aguarde o build terminar antes de fechar.")
            event.ignore()
            return
        self.settings.setValue("repo", self.repo_edit.text().strip())
        event.accept()


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
