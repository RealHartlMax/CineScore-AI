#ifndef MyAppVersion
  #error "MyAppVersion must be defined"
#endif

#ifndef SourceRoot
  #error "SourceRoot must be defined"
#endif

#ifndef OutputDir
  #error "OutputDir must be defined"
#endif

#define AppName "CineScore AI"
#define AppPublisher "RealHartlMax"
#define AppId "{{D8AC8CF3-510A-49CE-A9C1-C15CB8FA33DF}}"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#MyAppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={userappdata}\CineScore-AI\resolve-runtime
DefaultGroupName={#AppName}
OutputDir={#OutputDir}
OutputBaseFilename=CineScore-AI-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyMemo=yes
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#AppName}
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Files]
Source: "{#SourceRoot}\src\*"; DestDir: "{userappdata}\CineScore-AI\resolve-runtime\src"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceRoot}\scripts\resolve_entry.py"; DestDir: "{userappdata}\CineScore-AI\resolve-runtime\scripts"; Flags: ignoreversion
Source: "{#SourceRoot}\README.md"; DestDir: "{userappdata}\CineScore-AI\resolve-runtime"; Flags: ignoreversion
Source: "{#SourceRoot}\LICENSE"; DestDir: "{userappdata}\CineScore-AI\resolve-runtime"; Flags: ignoreversion
Source: "{#SourceRoot}\pyproject.toml"; DestDir: "{userappdata}\CineScore-AI\resolve-runtime"; Flags: ignoreversion

[UninstallDelete]
Type: files; Name: "{userappdata}\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility\CineScore AI.py"
Type: filesandordirs; Name: "{userappdata}\CineScore-AI\resolve-runtime"

[Code]
function LauncherText(const EntryScriptPath: string): string;
var
  NewLine: string;
begin
  NewLine := #13#10;
  Result :=
    'from __future__ import annotations' + NewLine +
    NewLine +
    'import os' + NewLine +
    'from pathlib import Path' + NewLine +
    NewLine +
    NewLine +
    'ENTRY_SCRIPT = Path(os.environ.get("CINESCORE_AI_RESOLVE_ENTRY", r"' + EntryScriptPath + '"))' + NewLine +
    NewLine +
    'if not ENTRY_SCRIPT.exists():' + NewLine +
    '    raise RuntimeError(' + NewLine +
    '        "Could not find the installed CineScore AI Resolve entry script at "' + NewLine +
    '        f"''{ENTRY_SCRIPT}''. Run the Resolve installer again."' + NewLine +
    '    )' + NewLine +
    NewLine +
    '_launcher_globals = globals()' + NewLine +
    '_launcher_globals["__file__"] = str(ENTRY_SCRIPT)' + NewLine +
    'exec(compile(ENTRY_SCRIPT.read_text(encoding="utf-8"), str(ENTRY_SCRIPT), "exec"), _launcher_globals, _launcher_globals)' + NewLine;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResolveScriptsDir: string;
  RuntimeDir: string;
  EntryScriptPath: string;
  LauncherPath: string;
begin
  if CurStep = ssInstall then begin
    RuntimeDir := ExpandConstant('{userappdata}\CineScore-AI\resolve-runtime');
    if DirExists(RuntimeDir) then begin
      DelTree(RuntimeDir, True, True, True);
    end;
  end;

  if CurStep = ssPostInstall then begin
    ResolveScriptsDir := ExpandConstant('{userappdata}\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility');
    EntryScriptPath := ExpandConstant('{userappdata}\CineScore-AI\resolve-runtime\scripts\resolve_entry.py');
    LauncherPath := ResolveScriptsDir + '\CineScore AI.py';

    ForceDirectories(ResolveScriptsDir);
    SaveStringToFile(LauncherPath, LauncherText(EntryScriptPath), False);
  end;
end;
