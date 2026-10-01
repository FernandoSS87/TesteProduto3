#!/usr/bin/env python3
"""Build incremental: compila apenas os arquivos alterados no git.

Uso:
  gitbuild.py                  # alterações locais (staged, unstaged, untracked)
  gitbuild.py --base main      # alterações desde o merge-base com main
  gitbuild.py --base HEAD~3 --head HEAD
  gitbuild.py --dry-run        # só mostra o que rodaria
"""
import argparse
import json
import os
import re
import shlex
import subprocess
import sys

DEFAULT_CONFIG = "gitbuild.json"



def _bundled_git_dir():
    """Pasta cmd/ do MinGit embutido pelo PyInstaller (ou ao lado do script), se existir."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    cmd_dir = os.path.join(base, "mingit", "cmd")
    return cmd_dir if os.path.isfile(os.path.join(cmd_dir, "git.exe")) else None


def _resolve_git():
    """GITBUILD_GIT > MinGit embutido > git do PATH."""
    if os.environ.get("GITBUILD_GIT"):
        return os.environ["GITBUILD_GIT"]
    cmd_dir = _bundled_git_dir()
    return os.path.join(cmd_dir, "git.exe") if cmd_dir else "git"


GIT_EXE = _resolve_git()


def _child_env():
    """Ambiente dos comandos de build: coloca o git embutido no PATH para regras que o chamem."""
    env = os.environ.copy()
    cmd_dir = _bundled_git_dir()
    if cmd_dir:
        env["PATH"] = cmd_dir + os.pathsep + env.get("PATH", "")
    return env

# Evita abrir janela de console ao chamar processos a partir do app gráfico no Windows.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def git(*args, repo=None):
    res = subprocess.run(
        [GIT_EXE, *args], capture_output=True, text=True, cwd=repo, creationflags=_NO_WINDOW
    )
    if res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {res.stderr.strip()}")
    return res.stdout


def changed_files(base=None, head="HEAD", repo=None):
    """Retorna os arquivos alterados (existentes) como lista ordenada."""
    if base:
        merge_base = git("merge-base", base, head, repo=repo).strip()
        out = git("diff", "--name-only", "--diff-filter=d", merge_base, head, repo=repo)
        files = set(out.splitlines())
    else:
        files = set()
        # diff contra HEAD cobre staged + unstaged; repo sem commits usa só o índice
        has_head = subprocess.run(
            [GIT_EXE, "rev-parse", "--verify", "-q", "HEAD"],
            capture_output=True, cwd=repo, creationflags=_NO_WINDOW,
        ).returncode == 0
        if has_head:
            files |= set(git("diff", "--name-only", "--diff-filter=d", "HEAD", repo=repo).splitlines())
        else:
            files |= set(git("diff", "--name-only", "--cached", repo=repo).splitlines())
        files |= set(git("ls-files", "--others", "--exclude-standard", repo=repo).splitlines())
    return sorted(f for f in files if f)


def load_config(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def glob_to_regex(pattern):
    """Converte glob com suporte a ** em regex."""
    i, out = 0, ""
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
            continue
        if pattern.startswith("**", i):
            out += ".*"
            i += 2
            continue
        if c == "*":
            out += "[^/]*"
        elif c == "?":
            out += "[^/]"
        else:
            out += re.escape(c)
        i += 1
    return re.compile(out + r"\Z")


def match_rule(rule, files):
    regexes = [glob_to_regex(p) for p in rule["patterns"]]
    return [f for f in files if any(r.match(f) for r in regexes)]


def plan(config, files):
    """Gera a lista de (nome, comando) a executar, sem duplicatas."""
    steps, seen = [], set()
    for rule in config["rules"]:
        matched = match_rule(rule, files)
        if not matched:
            continue
        template = rule["command"]
        if rule.get("per_file"):
            cmds = [template.replace("{file}", shlex.quote(f)) for f in matched]
        else:
            cmds = [template.replace("{files}", " ".join(shlex.quote(f) for f in matched))]
        for cmd in cmds:
            if cmd not in seen:
                seen.add(cmd)
                steps.append((rule.get("name", template), cmd))
    return steps


def run_step(cmd, cwd=None, on_line=None):
    """Executa um comando repassando cada linha de saída para on_line. Retorna o exit code."""
    proc = subprocess.Popen(
        cmd, shell=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, errors="replace", creationflags=_NO_WINDOW, env=_child_env(),
    )
    with proc.stdout:
        for line in proc.stdout:
            if on_line:
                on_line(line.rstrip("\r\n"))
    return proc.wait()


def run_plan(steps, cwd=None, on_line=None, on_step=None, keep_going=False):
    """Roda os passos em ordem. Retorna lista de dicts {name, command, returncode}."""
    results = []
    for name, cmd in steps:
        if on_step:
            on_step(name, cmd)
        rc = run_step(cmd, cwd=cwd, on_line=on_line)
        results.append({"name": name, "command": cmd, "returncode": rc})
        if rc != 0 and not keep_going:
            break
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".", help="pasta do repositório (padrão: atual)")
    ap.add_argument("--base", help="ref base (usa merge-base com --head)")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--config", default=None, help=f"padrão: <repo>/{DEFAULT_CONFIG}")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--keep-going", action="store_true", help="continua após falha")
    ap.add_argument("--json", action="store_true", help="imprime o plano/resultado em JSON")
    args = ap.parse_args(argv)

    repo = os.path.abspath(args.repo)
    config_path = args.config or os.path.join(repo, DEFAULT_CONFIG)
    try:
        config = load_config(config_path)
        files = changed_files(args.base, args.head, repo=repo)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 2

    steps = plan(config, files)

    if args.json:
        out = {"files": files, "steps": [{"name": n, "command": c} for n, c in steps]}
        if not args.dry_run:
            # stdout fica reservado ao JSON; a saída dos comandos vai para stderr
            out["results"] = run_plan(
                steps, cwd=repo, on_line=lambda l: print(l, file=sys.stderr), keep_going=args.keep_going
            )
        print(json.dumps(out, ensure_ascii=False, indent=2))
        failed = any(r["returncode"] != 0 for r in out.get("results", []))
        return 1 if failed else 0

    if not files:
        print("Nenhuma alteração para compilar.")
        return 0
    print(f"{len(files)} arquivo(s) alterado(s).")
    if not steps:
        print("Nenhuma regra correspondente às alterações.")
        return 0

    if args.dry_run:
        for name, cmd in steps:
            print(f"[{name}] $ {cmd}")
        print("Dry-run concluído.")
        return 0

    results = run_plan(
        steps, cwd=repo, on_line=print,
        on_step=lambda n, c: print(f"[{n}] $ {c}"), keep_going=args.keep_going,
    )
    failed = [r for r in results if r["returncode"] != 0]
    for r in failed:
        print(f"[{r['name']}] FALHOU (código {r['returncode']})", file=sys.stderr)
    if failed:
        return 1
    print("Build concluído.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
