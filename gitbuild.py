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
import re
import shlex
import subprocess
import sys

DEFAULT_CONFIG = "gitbuild.json"


def git(*args):
    res = subprocess.run(["git", *args], capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {res.stderr.strip()}")
    return res.stdout


def changed_files(base=None, head="HEAD"):
    """Retorna os arquivos alterados (existentes) como lista ordenada."""
    if base:
        merge_base = git("merge-base", base, head).strip()
        out = git("diff", "--name-only", "--diff-filter=d", merge_base, head)
        files = set(out.splitlines())
    else:
        files = set()
        # diff contra HEAD cobre staged + unstaged; repo sem commits usa só o índice
        has_head = subprocess.run(
            ["git", "rev-parse", "--verify", "-q", "HEAD"], capture_output=True
        ).returncode == 0
        if has_head:
            files |= set(git("diff", "--name-only", "--diff-filter=d", "HEAD").splitlines())
        else:
            files |= set(git("diff", "--name-only", "--cached").splitlines())
        files |= set(git("ls-files", "--others", "--exclude-standard").splitlines())
    return sorted(f for f in files if f)


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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", help="ref base (usa merge-base com --head)")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--keep-going", action="store_true", help="continua após falha")
    args = ap.parse_args(argv)

    try:
        with open(args.config, encoding="utf-8") as fh:
            config = json.load(fh)
        files = changed_files(args.base, args.head)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 2

    if not files:
        print("Nenhuma alteração para compilar.")
        return 0
    print(f"{len(files)} arquivo(s) alterado(s).")

    steps = plan(config, files)
    if not steps:
        print("Nenhuma regra correspondente às alterações.")
        return 0

    failed = 0
    for name, cmd in steps:
        print(f"[{name}] $ {cmd}")
        if args.dry_run:
            continue
        if subprocess.run(cmd, shell=True).returncode != 0:
            failed += 1
            print(f"[{name}] FALHOU", file=sys.stderr)
            if not args.keep_going:
                return 1
    if failed:
        return 1
    print("Build concluído." if not args.dry_run else "Dry-run concluído.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
