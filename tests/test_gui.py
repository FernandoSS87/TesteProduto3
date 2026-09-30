import os
import subprocess
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication
    import gitbuild_gui
except ImportError:  # PySide6 ausente: pula
    gitbuild_gui = None


@unittest.skipIf(gitbuild_gui is None, "PySide6 não instalado")
class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_repo(self, tmp):
        subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
        with open(os.path.join(tmp, "a.py"), "w") as fh:
            fh.write("x = 1\n")
        with open(os.path.join(tmp, "gitbuild.json"), "w") as fh:
            fh.write('{"rules":[{"name":"py","patterns":["*.py"],"command":"%s -m py_compile {files}"}]}'
                     % sys.executable.replace("\\", "/"))

    def wait(self, cond, ms=10000):
        loop = QEventLoop()
        timer = QTimer()
        timer.timeout.connect(lambda: loop.quit() if cond() else None)
        timer.start(50)
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    def test_refresh_and_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.make_repo(tmp)
            win = gitbuild_gui.MainWindow()
            win.repo_edit.setText(tmp)
            win.refresh()
            self.assertEqual(win.files_list.count(), 2)  # a.py + gitbuild.json
            self.assertEqual(len(win.steps), 1)
            self.assertTrue(win.build_btn.isEnabled())
            win.build()
            self.wait(lambda: win.thread is None)
            self.assertIn("Build concluído", win.log.toPlainText())
            win.close()

    def test_build_failure_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.make_repo(tmp)
            with open(os.path.join(tmp, "a.py"), "w") as fh:
                fh.write("def (:\n")
            win = gitbuild_gui.MainWindow()
            win.repo_edit.setText(tmp)
            win.refresh()
            win.build()
            self.wait(lambda: win.thread is None)
            self.assertIn("FALHOU", win.log.toPlainText())
            win.close()


if __name__ == "__main__":
    unittest.main()
