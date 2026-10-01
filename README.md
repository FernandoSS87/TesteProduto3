# GitBuild

Compila apenas os arquivos alterados no git. Regras em `gitbuild.json`.

## CLI
    python gitbuild.py                  # alterações locais
    python gitbuild.py --base main      # desde o merge-base com main
    python gitbuild.py --dry-run --json # plano em JSON

## Interface gráfica
    pip install -r requirements.txt
    python gitbuild_gui.py

## Aplicativo Windows (tudo embutido)
Na máquina de build (Windows, com Python):

    powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1

Gera `dist\GitBuild\GitBuild.exe` com Python, PySide6 e MinGit embutidos
(o usuário final não instala nada). Para um instalador, compile
`packaging\installer.iss` com o Inno Setup. O git usado é, em ordem:
`GITBUILD_GIT` > MinGit embutido > `git` do PATH.

Nota: os comandos das regras (npm, dotnet, etc.) usam as ferramentas
instaladas na máquina; só o git e o Python do app vêm embutidos.

## Testes
    python -m unittest discover -s tests
