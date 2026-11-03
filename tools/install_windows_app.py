"""Install per-user Windows shortcuts using the existing external environment."""
import base64
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from workbench_environment import (child_environment, environment_folder, require_runtime,
                                   validate_environment_location, retire_legacy_entrypoints)
from workbench_updates import POINTER, write_json

APP_FILES = ('tools/windows_app.py', 'tools/windows_server.py', 'tools/windows_process.py',
             'tools/update_bridge.py', 'tools/update_workbench.py', 'workbench_updates.py',
             'VERSION', 'windows/TensileWorkbench.ico')

# Paths are passed as environment data, never interpolated into PowerShell code.
# Inline commands do not require changing the user's script execution policy.
SHORTCUT_SCRIPT = r'''
$ErrorActionPreference = 'Stop'
$shell = New-Object -ComObject WScript.Shell
$description = 'Tensile Workbench desktop launcher'
$destinations = @(
    (Join-Path ($shell.SpecialFolders.Item('Desktop')) 'Tensile Workbench.lnk'),
    (Join-Path ($shell.SpecialFolders.Item('Programs')) 'Tensile Workbench.lnk')
)
foreach ($path in $destinations) {
    if (Test-Path -LiteralPath $path) {
        $existing = $shell.CreateShortcut($path)
        if ($existing.Description -ne $description) {
            throw "An unrelated shortcut already exists at $path. Rename it before installing."
        }
    }
}
foreach ($path in $destinations) {
    $shortcut = $shell.CreateShortcut($path)
    $shortcut.TargetPath = $env:TW_SHORTCUT_PYTHON
    $shortcut.Arguments = $env:TW_SHORTCUT_ARGUMENTS
    $shortcut.WorkingDirectory = $env:TW_SHORTCUT_ROOT
    $shortcut.IconLocation = $env:TW_SHORTCUT_ICON + ',0'
    $shortcut.Description = $description
    $shortcut.Save()
    Write-Host "Installed $path"
}
'''


def shortcut_environment(root, folder, environ=None):
    root, folder = Path(root).resolve(), Path(folder).resolve()
    validate_environment_location(folder, root)
    for name in APP_FILES:
        if not (root / name).is_file():
            raise RuntimeError('Missing ' + name + '. Extract the complete repository before installing.')
    python = folder / 'Scripts/pythonw.exe'
    if not python.is_file():
        raise RuntimeError('The windowed Python launcher is missing. Run Install_Tensile_Workbench_App.bat first.')
    env = dict(os.environ if environ is None else environ)
    env.update(TW_SHORTCUT_ROOT=str(root), TW_SHORTCUT_PYTHON=str(python),
               TW_SHORTCUT_ICON=str(root / 'windows/TensileWorkbench.ico'),
               TW_SHORTCUT_ARGUMENTS=subprocess.list2cmdline([
                   str(root / 'tools/windows_app.py'), '--environment', str(folder)]))
    return env


def install(root=ROOT, folder=None):
    require_runtime()
    if sys.platform != 'win32':
        raise RuntimeError('Use Install_Tensile_Workbench_App.command on macOS.')
    folder = folder or environment_folder(root)
    env = shortcut_environment(root, folder)
    # Tcl/Tk belongs to the Python installation, not a package downloaded by pip.
    subprocess.run([str(Path(folder) / 'Scripts/python.exe'), '-c',
                    'import tkinter as tk; w = tk.Tk(); w.withdraw(); w.destroy()'],
                   cwd=root, env=child_environment(folder), check=True)
    encoded = base64.b64encode(SHORTCUT_SCRIPT.encode('utf-16-le')).decode('ascii')
    subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
                   cwd=root, env=env, check=True)
    # A refreshed custom installation must also update the selection used by
    # older pinned shortcuts. They may still carry the previous --environment.
    if (Path(root) / POINTER).exists():
        write_json(Path(root) / POINTER, {'schema_version': 1, 'environment': str(Path(folder).resolve())})
    retire_legacy_entrypoints(root)
    print('Ready. Open Tensile Workbench from your desktop or Start menu.\n'
          'The control window has Start/Stop, Open Workbench and a live View log.\n'
          'Keep the code folder in place; rerun this installer if you move it.', flush=True)


if __name__ == '__main__':
    try:
        install()
    except Exception as error:
        print('Could not install the Windows app:', error, file=sys.stderr)
        print('Use the complete Python 3.14 installer with Tcl/Tk. See SETUP.md for help.', file=sys.stderr)
        raise SystemExit(1)
