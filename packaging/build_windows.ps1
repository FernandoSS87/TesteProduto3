<#
Gera dist\GitBuild\GitBuild.exe com Python, PySide6 e MinGit embutidos.
Rodar no Windows, na raiz do repositório:
    powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
Pré-requisito (só na máquina de build): Python 3.10+ no PATH.
O usuário final não precisa instalar nada.
#>
param(
    [string]$MinGitVersion = "2.47.1",
    [string]$MinGitTag = "v2.47.1.windows.1",
    # Recomendado: informe o SHA256 publicado na página da release do Git for Windows.
    [string]$MinGitSha256 = ""
)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

Write-Host "==> Ambiente virtual e dependências"
python -m venv .venv-build
& .\.venv-build\Scripts\python.exe -m pip install --upgrade pip
& .\.venv-build\Scripts\python.exe -m pip install -r requirements.txt pyinstaller

Write-Host "==> MinGit $MinGitVersion"
$zip = "build\MinGit.zip"
New-Item -ItemType Directory -Force build | Out-Null
if (-not (Test-Path $zip)) {
    $url = "https://github.com/git-for-windows/git/releases/download/$MinGitTag/MinGit-$MinGitVersion-64-bit.zip"
    Invoke-WebRequest -Uri $url -OutFile $zip
}
if ($MinGitSha256) {
    $hash = (Get-FileHash $zip -Algorithm SHA256).Hash
    if ($hash -ne $MinGitSha256.ToUpper()) { throw "SHA256 do MinGit não confere: $hash" }
} else {
    Write-Warning "MinGitSha256 não informado: download não verificado."
}
Remove-Item -Recurse -Force build\mingit -ErrorAction SilentlyContinue
Expand-Archive $zip -DestinationPath build\mingit

Write-Host "==> PyInstaller"
& .\.venv-build\Scripts\pyinstaller.exe --noconfirm --clean --windowed `
    --name GitBuild `
    --add-data "build\mingit;mingit" `
    --add-data "gitbuild.json;." `
    gitbuild_gui.py

Write-Host "==> Pronto: dist\GitBuild\GitBuild.exe"
Write-Host "Instalador (opcional): compile packaging\installer.iss com o Inno Setup."
