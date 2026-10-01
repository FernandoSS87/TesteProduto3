; Instalador opcional (Inno Setup 6). Rode antes packaging\build_windows.ps1.
[Setup]
AppName=GitBuild
AppVersion=0.1.0
DefaultDirName={autopf}\GitBuild
DefaultGroupName=GitBuild
OutputDir=..\dist
OutputBaseFilename=GitBuild-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "..\dist\GitBuild\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\GitBuild"; Filename: "{app}\GitBuild.exe"
Name: "{autodesktop}\GitBuild"; Filename: "{app}\GitBuild.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; Flags: unchecked
