import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gitbuild


def run(*args, cwd):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True)


class GlobTests(unittest.TestCase):
    def test_globstar(self):
        rule = {"patterns": ["**/*.py"]}
        self.assertEqual(gitbuild.match_rule(rule, ["a.py", "x/y/b.py", "c.js"]), ["a.py", "x/y/b.py"])

    def test_single_star_not_crossing_dirs(self):
        rule = {"patterns": ["src/*.py"]}
        self.assertEqual(gitbuild.match_rule(rule, ["src/a.py", "src/x/b.py"]), ["src/a.py"])


class PlanTests(unittest.TestCase):
    def test_batch_and_per_file(self):
        cfg = {"rules": [
            {"name": "b", "patterns": ["*.py"], "command": "c {files}"},
            {"name": "p", "patterns": ["*.json"], "command": "v {file}", "per_file": True},
        ]}
        steps = gitbuild.plan(cfg, ["a.py", "b.py", "x.json", "y.json", "z.txt"])
        self.assertEqual([c for _, c in steps], ["c a.py b.py", "v x.json", "v y.json"])


class GitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        run("git", "init", "-q", "-b", "main", cwd=self.d)
        run("git", "config", "user.email", "t@t", cwd=self.d)
        run("git", "config", "user.name", "t", cwd=self.d)
        self.old = os.getcwd()
        os.chdir(self.d)

    def tearDown(self):
        os.chdir(self.old)
        self.tmp.cleanup()

    def write(self, name, text="x=1\n"):
        with open(name, "w") as fh:
            fh.write(text)

    def test_local_changes_no_commits(self):
        self.write("a.py")
        self.assertEqual(gitbuild.changed_files(), ["a.py"])

    def test_local_changes_and_deleted_excluded(self):
        self.write("a.py"); self.write("b.py")
        run("git", "add", ".", cwd=self.d); run("git", "commit", "-qm", "i", cwd=self.d)
        self.write("a.py", "x=2\n"); os.remove("b.py"); self.write("c.py")
        self.assertEqual(gitbuild.changed_files(), ["a.py", "c.py"])

    def test_base_ref(self):
        self.write("a.py")
        run("git", "add", ".", cwd=self.d); run("git", "commit", "-qm", "i", cwd=self.d)
        run("git", "checkout", "-qb", "feat", cwd=self.d)
        self.write("n.py")
        run("git", "add", ".", cwd=self.d); run("git", "commit", "-qm", "f", cwd=self.d)
        self.assertEqual(gitbuild.changed_files("main"), ["n.py"])


class ResolveGitTests(unittest.TestCase):
    def test_env_overrides_then_bundled_then_path(self):
        old = os.environ.pop("GITBUILD_GIT", None)
        try:
            self.assertEqual(gitbuild._resolve_git(), "git")
            with tempfile.TemporaryDirectory() as tmp:
                cmd = os.path.join(tmp, "mingit", "cmd")
                os.makedirs(cmd)
                open(os.path.join(cmd, "git.exe"), "w").close()
                sys._MEIPASS = tmp
                try:
                    self.assertEqual(gitbuild._resolve_git(), os.path.join(cmd, "git.exe"))
                    self.assertTrue(gitbuild._child_env()["PATH"].startswith(cmd))
                    os.environ["GITBUILD_GIT"] = "custom"
                    self.assertEqual(gitbuild._resolve_git(), "custom")
                finally:
                    del sys._MEIPASS
        finally:
            os.environ.pop("GITBUILD_GIT", None)
            if old:
                os.environ["GITBUILD_GIT"] = old


class RunTests(unittest.TestCase):
    def test_run_step_streams_output_and_code(self):
        lines = []
        rc = gitbuild.run_step(f'{sys.executable} -c "print(1); print(2)"', on_line=lines.append)
        self.assertEqual((rc, lines), (0, ["1", "2"]))

    def test_run_plan_stops_on_failure(self):
        ok, bad = f'{sys.executable} -c "pass"', f'{sys.executable} -c "raise SystemExit(3)"'
        res = gitbuild.run_plan([("a", bad), ("b", ok)])
        self.assertEqual([r["returncode"] for r in res], [3])
        res = gitbuild.run_plan([("a", bad), ("b", ok)], keep_going=True)
        self.assertEqual([r["returncode"] for r in res], [3, 0])


if __name__ == "__main__":
    unittest.main()
