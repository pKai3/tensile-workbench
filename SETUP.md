# Setup on Windows and Mac

## First use

1. Clone the repository, or download the GitHub ZIP and **extract it completely**. Keep the code in a writable folder; do not run inside the ZIP. Data and output folders can be elsewhere and are chosen in the app. GitHub does not include research data.
2. The workbench uses standard **Python 3.14, 64-bit**. If it is missing, the next step offers to download and open its official installer. Complete its normal screens and close the installer; Workbench setup continues automatically. To install Python yourself instead:
   - **Windows x86-64:** use the [Python.org Windows downloads](https://www.python.org/downloads/windows/) and include the Python launcher and **Tcl/Tk and IDLE**. Do not use the embeddable or free-threaded build. This setup does not currently target Windows ARM64.
   - **Mac, Apple Silicon or Intel:** use the Python 3.14 **macOS 64-bit universal2 installer** from [Python.org](https://www.python.org/downloads/macos/). An existing standard Homebrew Python 3.14 also works. Finder's launcher checks normal Python.org and Homebrew locations even if its PATH is limited.
3. Double-click the setup file for your system:

   | System | Setup once / install missing dependencies | Open normally |
   | --- | --- | --- |
   | Windows | `Install_Tensile_Workbench_App.bat` | **Tensile Workbench** on the desktop or Start menu |
   | Mac | `Setup_Tensile_Workbench.command` | `Tensile Workbench.app` in your user Applications folder, or `Launch_Tensile_Workbench.command` |

4. Wait for **Setup complete**. Internet access is needed for package installation. Setup checks imports and analysis-definition validity but does not load research datasets, create plots, change definitions or start Jupyter.
5. Open the installed app. The web app opens in your browser and runs automatically—there is no notebook editor or Run All Cells step. Confirm the data/output folders on first use. The control window provides **Stop**. The server listens on this computer only (`127.0.0.1`). The existing `Setup_Tensile_Workbench.bat` and `Launch_Tensile_Workbench.bat` still support console-only use on Windows; leave that console open and press Ctrl-C to stop it.

The Python installer opens only after you accept the offer. macOS asks for administrator approval because the official package installs Python for all users. On Windows, the installer lets you choose a per-user or all-users installation; the latter normally needs administrator approval. Workbench packages still go in their own environment. On a managed computer, ask IT to approve Python/package access if blocked. The scripts do not change PowerShell execution policy or disable security protections.

### Guided Python installation

- Setup and the source-folder Launch files first look for an existing standard 3.14 interpreter. If found, no Python download is offered. If absent, accept **Install Python** on Mac or answer **Y** on Windows.
- The helper downloads the official **Python 3.14.10** installer from python.org, checks its published SHA-256, and opens the ordinary installer UI. Windows also checks the executable's signature. Licence acceptance, installation scope and administrator prompts stay in the normal OS workflow.
- On Windows, keep **Tcl/Tk** and the **Python launcher** selected. Setup checks standard install locations again afterwards, so a freshly changed PATH does not require another terminal. On Mac, the helper also runs Python's supplied **Install Certificates.command** to complete HTTPS setup.
- If the installation succeeds, setup resumes. A first Launch that needed Python also installs Workbench's packages before opening the app. Cancelling, a download/checksum failure, or an unsuccessful installer stops the process; rerun Setup to retry. Temporary installer files are removed after the attempt.
- Other Python versions and existing workbench environments are preserved. A launch with Python already installed still expects the Workbench environment to have been set up previously. The Mac Dock app can show the installer offer if its Python is missing; a Windows shortcut whose Python executable has been removed must be repaired through **Install_Tensile_Workbench_App.bat**.

Installer URLs and checksums are recorded together in `tools/python_installers.conf`, sourced from the [official release page](https://www.python.org/downloads/release/python-31410/). A future installer update must change both; helpers do not run an unverified replacement download.

## Windows desktop app

Double-click **Install_Tensile_Workbench_App.bat** on Windows 10/11 x86-64. It runs the normal environment setup, checks Tcl/Tk, and adds **Tensile Workbench** to your desktop and Start menu. Installation uses your own account and does not require administrator privileges. The setup console remains visible until finished; the installed shortcuts launch without a console. **Launch_Tensile_Workbench_App.bat** is an alternative entry point.

- The control window starts the server and opens your browser when ready. **Open Workbench** uses the current authenticated address; **Start/Stop** restarts or stops this instance.
- Keep the window open or minimised. **Stop** and closing the window ask for confirmation, then stop this server and its calculation processes. Closing just the browser or live-log window leaves the server running.
- **View log** shows recent output, updates live and follows new output unless you scroll back. **Copy log** copies the displayed text. Browser access tokens are hidden. Logs retain up to 2 MB plus one rotated file; the viewer displays the most recent 128 KiB.
- A second launch from the same code folder points you to the existing control window. The app does not adopt or stop a separately launched console server or another installation. Stop an old console session with Ctrl-C before switching to the app.
- If **Tcl/Tk** is missing, modify your Python installation to include it, then rerun the app installer. The console launcher remains available without Tcl/Tk.

The shortcuts use the downloaded code folder and external Python environment. Keep both folders in place. Use **Check for updates** for normal updates; it handles the environment and shortcuts. Rerun the installer after moving the code folder or manually changing the environment. Installation and shortcut updates preserve personal project settings and data.

The source, icon and installer are included in Git; shortcuts contain local paths and are created only on your computer. See [Windows launcher notes](windows/README.md) for implementation and verification details.

## Mac Dock app

The optional native launcher requires **macOS 13 or newer** and **Apple Command Line Tools** (or Xcode). Setup builds it after Python setup succeeds. If the build tools are missing, run `xcode-select --install` in Terminal and complete Apple's installer, then double-click **Install_Tensile_Workbench_App.command**. Full Xcode is not required. This adds a build-tool download; it is not needed if you prefer the existing Terminal launcher. On older macOS, the Dock app is unavailable; use the Terminal launcher if the Python/dependency installation supports your system.

- The app is installed in **~/Applications/Tensile Workbench.app**, without administrator privileges. In Finder, choose Go → Go to Folder and enter `~/Applications`, then drag the app to your Dock.
- **Open Workbench** reopens the browser using the current server's authenticated address.
- **View log** opens a resizable window inside the app, updating twice a second. Untick Auto-scroll to inspect earlier messages; Jump to latest resumes following. Copy log copies the displayed text. The viewer keeps a bounded recent tail; logs may contain a local access token, so check them before sharing.
- Closing the launcher/log window does **not** stop the server. **Stop** or **Quit** asks for confirmation and stops only the server started by this app, allowing its kernels to close. Save work before stopping.
- A server already running from this same checkout in Terminal is not adopted or stopped automatically. Stop it with Ctrl-C, then click Start in the app.
- Quit the Dock app before installing an update. The installer refuses to replace a running launcher. Existing app contents are backed up under **~/Library/Application Support/Tensile Workbench/launcher-backups/**. No source data or personal settings are moved.

The installed app uses your existing checkout and Python environment. It is **not a portable copy of the whole workbench**. Git contains `macos/Launcher.swift`, a generic `macos/Info.plist`, the icon and the installer; installation fills in local paths only in the built app. Build/signing is local (ad-hoc), not an Apple-notarised downloadable binary. Keep normal macOS security protections enabled.

After pulling/unzipping updates, run **Install_Tensile_Workbench_App.command** to update just the launcher. With Python already available, it neither installs packages nor starts the server. If Python is missing, the guided installation above completes Python and Workbench setup first. Rerunning Setup also updates the launcher. If the checkout moves, rerun the installer from the new location. Apple Silicon and Intel Macs build for their own architecture. Temporary compiler caches are removed after the build, including on failure.

## Existing installations and updates

### Built-in updates and recovery

Both desktop launchers offer **Check for updates** and check GitHub's latest
published release in the background at startup. Checks do not install anything
or interrupt calculations. Offline checks fail quietly. Use the button to read
release notes and choose **Install update and restart**; save pending edits first.

The updater downloads the versioned release asset, checks GitHub's SHA-256 digest
and the package's file hashes, then checks the staged application. If requirements
changed, it prepares and checks a separate environment before stopping the old
app. It then stops its own server, backs up the existing code/settings, replaces
only application files, refreshes the launcher and restarts. Other server or
notebook sessions using the same folder must be closed first. Runtime changes
beyond Python 3.14 require the new installer instead of an automatic update.

- **Windows ZIP installations:** no Git, GitHub sign-in or administrator access
  is needed when the application folder is writable. Use the named
  **Tensile-Workbench-x.y.z.zip** release asset. A GitHub-generated source ZIP can
  also update once its files are verified against its original numbered release.
- **Git checkouts on either system:** updates advance to the official release
  commit only when it is a fast-forward and tracked files have no local changes.
  Untracked files that collide with new release files also stop the update.
  A development branch ahead of/diverged from the release needs manual Git
  handling. The updater never runs a destructive reset or discards local edits.
- **Mac:** the updater rebuilds the native launcher using the same Command Line
  Tools needed for its initial installation. It compiles before stopping the app.
- **Preserved:** personal project settings, overrides, variables, folder choices,
  research data/output, unknown local files and previous environments. The code
  folder stays in place, so relative data paths retain their meaning.

For an installation failure, the updater restores the previous code, environment
selection and launcher. A crash or power interruption leaves an update lock;
ordinary startup refuses to run a half-replaced installation. **Check for updates**
then offers **Restore previous version and restart**. If the launcher itself
cannot open, use **Recover Tensile Workbench.bat** (Windows) or **Recover Tensile
Workbench.command** (Mac) in the transaction's backup folder below. Close other
Workbench sessions first. Recovery checks backup hashes and refuses to overwrite
subsequent code edits. Settings snapshots are retained separately; code recovery
does not overwrite personal settings edited afterwards.

Updates keep their logs, previous code and settings snapshots in a per-installation
folder:

| Windows | Mac |
| --- | --- |
| `%LOCALAPPDATA%\TensileWorkbench\updates\<installation ID>\<version-ID>\` | `~/Library/Application Support/Tensile Workbench/updates/<installation ID>/<version-ID>/` |

The transaction folder contains `update.log`, `transaction.json`, `backup/` and
`saved-settings/`. A changed dependency set lives in `runtime/venv` there; **do not
delete update folders while their environment is in use**. The ignored
`.tensile-environment.json` in the code folder records the active environment.
An explicit `TENSILE_ENV_DIR` still takes priority for command-line launches.
These update backups are separate from the automatic settings-history vault.

**One-time adoption:** existing users must first close the app, pull/copy this
release's source into the existing code folder and rerun the app installer.
Preserve personal project/path settings, data and output; do not delete the whole
folder. Subsequent numbered releases can be installed from the launcher.

### Manual setup and Python upgrades

**This version uses Python 3.14.** Close the running workbench, then run **Install_Tensile_Workbench_App.bat** on Windows or **Setup_Tensile_Workbench.command** on Mac. Accept the Python installer if offered. Setup creates or reuses the `py314/venv` environment. Windows app installation refreshes shortcuts to use it. Mac launchers select it automatically on the next start.

Older `venv` and Windows `v17-py313-…/venv` environments are left untouched, together with their caches. They are no longer selected automatically. Python environments are not renamed, copied or upgraded in place. The old environment remains available with the older code if rollback is needed. Your project file, overrides, backups and folder preferences remain in their existing locations.

If you use **TENSILE_ENV_DIR**, choose a new external folder for the 3.14 environment, then rerun Setup and the app installer with that value. Pointing it at an old 3.13 environment stops before packages are changed. Repeated setup and additional code checkouts reuse the same 3.14 environment by default.

Before running Setup or pulling code updates, close workbench browser tabs/notebooks and stop their launchers. Setup installs from `requirements.txt`, retains already-compatible packages (no blanket upgrade), checks dependency consistency, and registers the **Tensile Workbench** kernel inside that environment. Rerun Setup if Launch reports a missing/incompatible dependency, or an update changes requirements. Launch itself never installs packages.

Normal Launch checks installed package versions and saved definitions without importing the entire numerical/UI stack twice. Setup and the explicit `check` command below retain the full import checks. Opening the app still starts a Python kernel, loads the selected groups' property tables and, if Live preview is enabled, calculates the saved plot views. Wait for that first load; refreshing starts a new session and repeats this work.

`requirements-windows.txt` is a historical record of the previous Python 3.13 environment and is not used by current installers. Both systems use `requirements.txt`. Exact installed versions are recorded locally in `installed-packages.txt` beside the selected environment; dependency ranges are not a fully locked reproducible environment.

## Where files go

| Item | Windows | Mac |
| --- | --- | --- |
| Python 3.14 environment | `%LOCALAPPDATA%\TensileWorkbench\py314\venv` | `~/Library/Application Support/Tensile Workbench/py314/venv` |
| Previous environments preserved | Earlier `venv` and `v17-py313-<fingerprint>\venv` folders | Earlier `~/Library/Application Support/Tensile Workbench/venv` |
| Update backups / changed dependencies | `%LOCALAPPDATA%\TensileWorkbench\updates\<installation ID>\` | `~/Library/Application Support/Tensile Workbench/updates/<installation ID>/` |
| Jupyter/configuration caches | Beside the selected environment | Beside the selected environment |
| Code and analysis definitions | Your downloaded/cloned folder | Your downloaded/cloned folder |
| Desktop app | Per-user Desktop and Start-menu shortcuts | `~/Applications/Tensile Workbench.app` |
| Desktop app logs | `%LOCALAPPDATA%\TensileWorkbench\logs\<checkout ID>\launcher.log` and `.log.1` | `~/Library/Logs/Tensile Workbench/launcher.log` (one previous launch retained) |
| Data and output | Your chosen folders | Your chosen folders |

No environment is created in the repository or OneDrive. Setup also refuses known cloud-storage locations or an environment overlapping the code folder. Do not set a custom environment inside a differently named synced folder; the scripts cannot discover every third-party sync configuration. Environments are local installations, not files to copy between computers. See Python's [virtual-environment documentation](https://docs.python.org/3.14/library/venv.html).

Both systems accept `TENSILE_ENV_DIR` as an **absolute path to the environment itself**, not its parent. Set it in the process launching Setup/Launch whenever using a non-default location. The Windows app installer records that environment in its shortcuts; the Mac installer records it in the locally built Dock app. Rerun the appropriate app installer with the new value to change it. Without an explicit override, launches use the updater's saved environment if present, otherwise the default above. Ordinary users do not need this setting.

## Troubleshooting

- **Missing Python:** accept setup's installer offer, or install the supported Python version above manually and rerun Setup. Both systems check the selected environment and standard installation locations. Windows also checks the Python launcher and PATH; Mac also checks Python.org and Homebrew. If installation was cancelled, setup stops without repeatedly prompting.
- **Windows shortcut does not open:** double-click `Launch_Tensile_Workbench_App.bat` for visible startup errors. Check that the code folder and Python environment still exist, then rerun the app installer. If the control window opens but the server stops, use **View log**. A missing Tcl/Tk component requires modifying the Python installation, not installing a pip package.
- **Mac command file permission:** if the downloaded ZIP lost executable permissions, open Terminal, type `/bin/zsh `, drag the Setup `.command` file into the window, then press Return. Use the same approach for Launch. If macOS blocks the download with a security warning, review it through the normal macOS approval workflow or ask IT; do not disable Gatekeeper.
- **Mac Dock app was not installed:** Python setup can still succeed. Follow the build-tool message above, quit any running Dock app and run Install_Tensile_Workbench_App.command again. A broken or unrecognised app at the destination is not overwritten; preserve or move it deliberately before retrying. The installer never launches the server or changes your environment.
- **Network/package failure:** retry Setup when network access is restored. Packages are installed without a persistent pip download cache; setup uses binary wheels and will report an error instead of starting a lengthy source build. Do not disable certificate verification. For Python.org certificate errors on Mac, follow the Python installer's certificate instructions or ask IT.
- **Partial installation:** if the environment's Python exists, Setup can retry missing packages. If the interpreter is missing/broken but the directory contains files, the script stops instead of overwriting it. Close all workbench sessions; rename that **specific environment folder** as a backup and rerun Setup. Keep the backup until the replacement works; do not rename/delete research folders.
- **App fails to load / missing kernel:** rerun Setup, then close and reopen Launch. The app runs automatically through Voilà using the environment's `python3` kernel. Users do not need to choose a kernel. Advanced notebook access is still available with `python launch_workbench.py --notebook`; in that mode select **Tensile Workbench** and Run All Cells. Kernel registration uses `--sys-prefix`, not a global user kernel. See [IPython's kernel documentation](https://ipython.readthedocs.io/en/stable/install/kernel_install.html).
- **Cloud-only code:** download the project files locally before launch. The preflight detects macOS cloud-only placeholders where the filesystem exposes them. Data must also be locally accessible when you analyse it.
- **Invalid definitions:** a validation error never resets or overwrites your JSON. Preserve your file and resolve the reported problem or restore an intentional backup.

## Web-app operation

Launch serves the existing widgets using [Voilà](https://voila.readthedocs.io/en/latest/using.html). It binds to `127.0.0.1` and enables a generated login token, which is included in the automatically opened browser URL. If a browser asks for a token, use **Open Workbench** in the app, or the URL printed by the console launcher. Do not turn authentication off or expose the service directly to the internet.

The small `workbench_server.py` wrapper corrects Voilà 0.5's tokenless browser redirect. It opens the authenticated URL using the actual available port, without changing the installed package or disabling authentication. No setup rerun is needed for this code-only fix. A cleared/expired login-cookie warning can occur after restarting the server; the new token link establishes a fresh login.

Close unused tabs; each page load starts a session. Disconnected idle kernels are cleaned up after 30 minutes. Keep one editing session per project to avoid conflicting saves. Refreshing/reopening restores saved analysis definitions, not temporary plot zoom. Stop and restart Launch after updates. Docker/remote deployment is not included in these local launchers.

## Checks without plots

Using Python 3.14 from any working directory:

```text
python /path/to/tensile-workbench/workbench_environment.py check
```

This finds the selected environment and checks dependencies/imports/definitions without installing anything or starting the web app. Automated tests use temporary synthetic folders and mock installation commands; they do not run pip or analyse research data. Windows-specific path/launch behavior is tested in simulation on Mac; a real Windows installation remains a colleague-side smoke test.
