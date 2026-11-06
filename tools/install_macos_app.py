"""Build/install the local Dock launcher; never install packages or launch Workbench."""
from __future__ import annotations

import os
from pathlib import Path
import platform
import plistlib
import shutil
import subprocess
import sys
import tempfile
import argparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
APP_NAME = 'Tensile Workbench.app'
BUNDLE_ID = 'local.tensileworkbench.launcher'
# Bump when compiler flags or the deployment target change. Older bundles used
# the same recipe, so their bundled source can still establish a safe match.
BUILD_RECIPE = 1


def run(command, **kwargs):
    return subprocess.run([str(item) for item in command], check=True, text=True, **kwargs)


def require_build_tools():
    if sys.platform != 'darwin':
        raise RuntimeError('This installer is for macOS. Use Install Tensile Workbench - Windows.bat on Windows.')
    if int(platform.mac_ver()[0].split('.')[0]) < 13:
        raise RuntimeError('The Dock app requires macOS 13 or newer. See the console workflow in SETUP.md for older systems.')
    try:
        run(['/usr/bin/xcode-select', '-p'], capture_output=True)
        run(['/usr/bin/xcrun', '--find', 'swiftc'], capture_output=True)
    except subprocess.CalledProcessError as error:
        raise RuntimeError(
            'The Dock app needs Apple Command Line Tools (or Xcode). In Terminal, run '
            'xcode-select --install and finish Apple’s installation, then double-click '
            'Install Tensile Workbench - macOS.command. See SETUP.md for the console workflow.'
        ) from error


def check_app_stopped():
    # Do not replace the executable/resources of a running Dock app. This reads
    # process executable names only, never command arguments containing tokens.
    result = run(['/bin/ps', '-axo', 'comm='], capture_output=True)
    if any(line.strip() == 'TensileWorkbench'
           or line.strip().endswith('/' + APP_NAME + '/Contents/MacOS/TensileWorkbench')
           for line in result.stdout.splitlines()):
        raise RuntimeError('Quit Tensile Workbench from its app menu first, then rerun this installer. '
                           'Closing its window does not quit the app. Nothing was stopped automatically.')


def validate_destination(destination):
    if destination.is_symlink():
        raise RuntimeError(f'Refusing to replace an app symlink: {destination}')
    if not destination.exists():
        return
    info = destination / 'Contents/Info.plist'
    try:
        if (destination / 'Contents').is_symlink():
            raise ValueError('symlinked Contents')
        metadata = plistlib.loads(info.read_bytes())
        if not isinstance(metadata, dict) or metadata.get('CFBundleIdentifier') != BUNDLE_ID:
            raise ValueError('different bundle identifier')
    except (OSError, ValueError, plistlib.InvalidFileException) as error:
        raise RuntimeError(f'An unrecognised item already exists at {destination}; it was not overwritten.') from error


def reusable_launcher(app, root, architecture, launch_root):
    """Reuse only a signed, matching native binary from this installation."""
    if not app:
        return None
    app = Path(app)
    try:
        validate_destination(app)
        contents = app / 'Contents'
        metadata = plistlib.loads((contents / 'Info.plist').read_bytes())
        if (metadata.get('WorkbenchBuildRecipe', 1) != BUILD_RECIPE
                or metadata.get('LSMinimumSystemVersion') != '13.0'
                or metadata.get('WorkbenchLauncherPath') != str(Path(launch_root) / 'Launch Tensile Workbench - macOS.command')):
            return None
        binary = contents / 'MacOS/TensileWorkbench'
        if not binary.is_file() or binary.is_symlink():
            return None
        if (contents / 'Resources/Launcher.swift').read_bytes() != (Path(root) / 'macos/Launcher.swift').read_bytes():
            return None
        run(['/usr/bin/codesign', '--verify', '--strict', app], capture_output=True)
        run(['/usr/bin/lipo', binary, '-verify_arch', architecture], capture_output=True)
        return binary
    except (OSError, ValueError, RuntimeError, plistlib.InvalidFileException, subprocess.CalledProcessError):
        return None


def build_bundle(root, build_directory, environ=None, architecture=None, launch_root=None, reuse_app=None):
    """Machine-specific paths are generated only inside this temporary bundle."""
    root = Path(root).resolve()
    build_directory = Path(build_directory)
    environ = os.environ if environ is None else environ
    architecture = architecture or platform.machine()
    if architecture not in ('arm64', 'x86_64'):
        raise RuntimeError(f'Unsupported Mac architecture: {architecture}')
    required = ('macos/Launcher.swift', 'macos/Info.plist', 'macos/TensileWorkbench.icns',
                'LICENSE', 'Launch Tensile Workbench - macOS.command', 'tools/run_macos.sh',
                'workbench_server.py', 'workbench_environment.py')
    for name in required:
        if not (root / name).is_file():
            raise RuntimeError(f'Missing {name}. Download/extract the complete repository before installing.')
    metadata = plistlib.loads((root / 'macos/Info.plist').read_bytes())
    if (root / 'VERSION').is_file():
        metadata['CFBundleShortVersionString'] = (root / 'VERSION').read_text().strip()
        metadata['CFBundleVersion'] = metadata['CFBundleShortVersionString']
    metadata['WorkbenchLauncherPath'] = str(Path(launch_root or root) / 'Launch Tensile Workbench - macOS.command')
    metadata['WorkbenchBuildRecipe'] = BUILD_RECIPE
    if environ.get('TENSILE_ENV_DIR'):
        # Finder does not inherit a Terminal's custom environment setting.
        sys.path.insert(0, str(root))
        try:
            from workbench_environment import environment_folder, validate_environment_location
            environment = environment_folder(root, 'darwin', environ)
            validate_environment_location(environment, root, environ)
        finally:
            sys.path.pop(0)
        metadata['WorkbenchEnvironmentPath'] = str(environment)

    app = build_directory / APP_NAME
    contents = app / 'Contents'
    resources = contents / 'Resources'
    resources.mkdir(parents=True)
    (contents / 'MacOS').mkdir()
    (contents / 'Info.plist').write_bytes(plistlib.dumps(metadata))
    for source, name in (('macos/TensileWorkbench.icns', 'TensileWorkbench.icns'),
                         ('macos/Launcher.swift', 'Launcher.swift'), ('LICENSE', 'LICENSE')):
        shutil.copyfile(root / source, resources / name)
    binary = reusable_launcher(reuse_app, root, architecture, launch_root or root)
    if binary is not None:
        print('Reusing unchanged Mac launcher.', flush=True)
        shutil.copy2(binary, contents / 'MacOS/TensileWorkbench')
    else:
        print('Compiling Mac launcher…', flush=True)
        run(['/usr/bin/xcrun', 'swiftc', '-O', '-target', architecture + '-apple-macos13.0',
             '-module-cache-path', build_directory / 'module-cache', '-framework', 'AppKit',
             root / 'macos/Launcher.swift', '-o', contents / 'MacOS/TensileWorkbench'])
    run(['/usr/bin/codesign', '--force', '--sign', '-', app])
    run(['/usr/bin/codesign', '--verify', '--strict', app])
    return app


def install_bundle(built_app, destination, backup_root):
    """Preserve the .app directory for Dock bookmarks; back up/replace Contents."""
    destination, backup_root = Path(destination), Path(backup_root)
    check_app_stopped()
    validate_destination(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Stage on the destination filesystem before touching an existing app.
    with tempfile.TemporaryDirectory(prefix='.tensile-install-', dir=destination.parent) as staging:
        staged_app = Path(staging) / APP_NAME
        shutil.copytree(built_app, staged_app)
        run(['/usr/bin/codesign', '--verify', '--strict', staged_app])
        check_app_stopped()
        validate_destination(destination)
        backup = None
        existed = destination.exists()
        if existed:
            backup_root.mkdir(parents=True, exist_ok=True)
            backup = Path(tempfile.mkdtemp(prefix='before-update-', dir=backup_root))
            shutil.move(destination / 'Contents', backup / 'Contents')
        else:
            destination.mkdir()
        try:
            (staged_app / 'Contents').replace(destination / 'Contents')
        except OSError:
            if backup is not None:
                shutil.move(backup / 'Contents', destination / 'Contents')
            elif not existed:
                destination.rmdir()  # Empty directory made by this installer only.
            raise
    return backup


def main():
    require_build_tools()
    check_app_stopped()
    user_home = Path.home()
    destination = user_home / 'Applications' / APP_NAME
    validate_destination(destination)
    print('Preparing the Dock app for this Mac. No data will be processed.', flush=True)
    # The temporary compiler cache can be large. Always remove it, including
    # on build failure; never leave it in the checkout or a synced data folder.
    with tempfile.TemporaryDirectory(prefix='tensile-macos-app-') as directory:
        app = build_bundle(ROOT, directory, reuse_app=destination)
        backup = install_bundle(app, destination,
                                user_home / 'Library/Application Support/Tensile Workbench/launcher-backups')
    registrar = Path('/System/Library/Frameworks/CoreServices.framework/Frameworks/'
                     'LaunchServices.framework/Support/lsregister')
    if registrar.is_file():
        try:
            run([registrar, '-f', destination], capture_output=True)
        except subprocess.CalledProcessError:
            print('App installed; macOS will register it when you open it.', flush=True)
    print(f'Installed: {destination}\nUses this workbench folder: {ROOT}', flush=True)
    if backup:
        print(f'Previous app contents kept at: {backup}', flush=True)
    print('Open the app in Finder and drag it to the Dock. View log opens a live log window.\n'
          'Closing the launcher window leaves it running; Quit stops its server.\n'
          'The app has not been launched. Data and personal settings are unchanged.', flush=True)
    from workbench_environment import retire_legacy_entrypoints
    retire_legacy_entrypoints(ROOT)
    return 0


if __name__ == '__main__':
    try:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('--check', action='store_true', help='Check prerequisites without installing anything')
        if parser.parse_args().check:
            require_build_tools()
            check_app_stopped()
            validate_destination(Path.home() / 'Applications' / APP_NAME)
            raise SystemExit(0)
        raise SystemExit(main())
    except KeyboardInterrupt:
        print('\nApp installation cancelled.', file=sys.stderr)
        raise SystemExit(130)
    except Exception as error:
        print(f'\nCould not install the Dock app: {error}', file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr)
        print('See SETUP.md for installation help and the console workflow.', file=sys.stderr)
        raise SystemExit(1)
