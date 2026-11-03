# Setup on Windows and Mac

## First use

1. Clone the repository, or download the GitHub ZIP and **extract it completely**. Keep the code in a writable folder; do not run inside the ZIP. Data and output folders can be elsewhere and are chosen in the app. GitHub does not include research data.
2. The workbench uses standard **Python 3.14, 64-bit**. If it is missing, the next step offers to download and open its official installer. Complete its normal screens and close the installer; Workbench setup continues automatically. To install Python yourself instead:
   - **Windows x86-64:** use the [Python.org Windows downloads](https://www.python.org/downloads/windows/) and include the Python launcher and **Tcl/Tk and IDLE**. Do not use the embeddable or free-threaded build. This setup does not currently target Windows ARM64.
   - **Mac, Apple Silicon or Intel:** use the Python 3.14 **macOS 64-bit universal2 installer** from [Python.org](https://www.python.org/downloads/macos/). An existing standard Homebrew Python 3.14 also works. Finder's launcher checks normal Python.org and Homebrew locations even if its PATH is limited.
3. Double-click the installer for your system:

   | System | Install once / repair | Open normally |
   | --- | --- | --- |
   | Windows | `Install_Tensile_Workbench_App.bat` | **Tensile Workbench** on the desktop or Start menu |
   | Mac | `Install_Tensile_Workbench_App.command` | `Tensile Workbench.app` in your user Applications folder, or `Launch_Tensile_Workbench.command` |

4. Wait for the installer to finish. It prepares the Python environment and desktop launcher together. Internet access is needed for package installation. It checks imports and analysis-definition validity without loading research datasets, creating plots or changing definitions.
5. Open the installed app. The web app opens in your browser and runs automatically—there is no notebook editor or Run All Cells step. Confirm the data/output folders on first use. The control window provides **Stop** and **Check for updates**. The server listens on this computer only (`127.0.0.1`).

The Python installer opens only after you accept the offer. macOS asks for administrator approval because the official package installs Python for all users. On Windows, the installer lets you choose a per-user or all-users installation; the latter normally needs administrator approval. Workbench packages still go in their own environment. On a managed computer, ask IT to approve Python/package access if blocked. The scripts do not change PowerShell execution policy or disable security protections.

### Guided Python installation

- The app installer first looks for an existing standard 3.14 interpreter. If found, no Python download is offered. If absent, accept **Install Python** on Mac or answer **Y** on Windows.
- The helper downloads the official **Python 3.14.10** installer from python.org, checks its published SHA-256, and opens the ordinary installer UI. Windows also checks the executable's signature. Licence acceptance, installation scope and administrator prompts stay in the normal OS workflow.
- On Windows, keep **Tcl/Tk** and the **Python launcher** selected. Setup checks standard install locations again afterwards, so a freshly changed PATH does not require another terminal. On Mac, the helper also runs Python's supplied **Install Certificates.command** to complete HTTPS setup.
- If Python installation succeeds, Workbench installation resumes. Cancelling, a download/checksum failure, or an unsuccessful installer stops the process; rerun **Install_Tensile_Workbench_App** to retry. Temporary installer files are removed after the attempt.
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

The native launcher requires **macOS 13 or newer** and **Apple Command Line Tools** (or Xcode). **Install_Tensile_Workbench_App.command** checks these prerequisites, sets up the Python environment and builds the app. It refuses to change packages while the Dock app is running. If build tools are missing, run `xcode-select --install` in Terminal, complete Apple's installer and rerun the Workbench installer. Full Xcode is not required. On older macOS, use the advanced console workflow below if Python supports your system.

- The app is installed in **~/Applications/Tensile Workbench.app**, without administrator privileges. In Finder, choose Go → Go to Folder and enter `~/Applications`, then drag the app to your Dock.
- **Open Workbench** reopens the browser using the current server's authenticated address.
- **View log** opens a resizable window inside the app, updating twice a second. Untick Auto-scroll to inspect earlier messages; Jump to latest resumes following. Copy log copies the displayed text. The viewer keeps a bounded recent tail; logs may contain a local access token, so check them before sharing.
- Closing the launcher/log window does **not** stop the server. **Stop** or **Quit** asks for confirmation and stops only the server started by this app, allowing its kernels to close. Save work before stopping.
- A server already running from this same checkout in Terminal is not adopted or stopped automatically. Stop it with Ctrl-C, then click Start in the app.
- Quit the Dock app before installing an update. The installer refuses to replace a running launcher. Existing app contents are backed up under **~/Library/Application Support/Tensile Workbench/launcher-backups/**. No source data or personal settings are moved.

The installed app uses your existing checkout and Python environment. It is **not a portable copy of the whole workbench**. Git contains `macos/Launcher.swift`, a generic `macos/Info.plist`, the icon and the installer; installation fills in local paths only in the built app. Build/signing is local (ad-hoc), not an Apple-notarised downloadable binary. Keep normal macOS security protections enabled.

After a manual code update or moving the checkout, rerun **Install_Tensile_Workbench_App.command**. It checks the Python environment and refreshes the launcher together. Normal **Check for updates** installs already handle this. Apple Silicon and Intel Macs build for their own architecture. Temporary compiler caches are removed after the build, including on failure.

## Advanced console use

The normal source folder has one installer and one app-launch file per system.
Console-only setup/launch remain internal commands for troubleshooting. From the
application folder, run:

| Action | Windows Command Prompt | Mac Terminal |
| --- | --- | --- |
| Prepare Python packages only | `tools\run_windows.bat setup` | `/bin/zsh tools/run_macos.sh setup` |
| Start a console server | `tools\run_windows.bat launch` | `/bin/zsh tools/run_macos.sh launch` |
| Rebuild only the Mac launcher | — | `/bin/zsh tools/run_macos.sh app` |

Leave that console open while working; **Ctrl-C** stops its server. The Mac
source-folder `Launch_Tensile_Workbench.command` opens the installed desktop app;
it checks that the app belongs to this checkout. Old Dock launchers can still
start their owned server through the same file without reopening themselves.

Updates remove the old duplicate Setup/console launch wrappers. After a manual
ZIP copy, the installer also retires unchanged stock wrappers left in the folder,
keeping their originals under `updates/<installation ID>/legacy-launchers/` in
the app's local support folder. Customised scripts and symlinks are preserved.

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
- **Copied folders without Git installed:** a leftover `.git` folder does not
  require installing Git. The updater verifies the existing files against the
  installed manifest or original published release and installs the new release
  directly. It retains Git metadata unchanged, together with personal settings
  and data. That installation keeps using release updates if Git is installed
  later. Windows text line-ending differences are accepted; code edits are not.
- **Git checkouts on either system:** updates advance to the official release
  commit only when it is a fast-forward and tracked files have no local changes.
  Untracked files that collide with new release files also stop the update.
  A development branch ahead of/diverged from the release needs manual Git
  handling. The updater never runs a destructive reset or discards local edits.
  This route is used when Git is available and the installation has not adopted
  release updates. Git retained by a copied installation is a historical copy;
  release updates do not advance its branch or commits.
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

**Older updater reports WinError 2:** this is fixed in version 1.0.2. Close the app,
copy that release ZIP into the existing application folder and rerun the app
installer once. Preserve personal settings, data and output. Do not install Git
just to repair this error.

### Manual setup and Python upgrades

**This version uses Python 3.14.** Close the running workbench, then run **Install_Tensile_Workbench_App.bat** on Windows or **Install_Tensile_Workbench_App.command** on Mac. Accept the Python installer if offered. The installer creates or reuses the `py314/venv` environment and refreshes the desktop launcher.

Older `venv` and Windows `v17-py313-…/venv` environments are left untouched, together with their caches. They are no longer selected automatically. Python environments are not renamed, copied or upgraded in place. The old environment remains available with the older code if rollback is needed. Your project file, overrides, backups and folder preferences remain in their existing locations.

If you use **TENSILE_ENV_DIR**, choose a new external folder for the 3.14 environment, then rerun the app installer with that value. Pointing it at an old 3.13 environment stops before packages are changed. Repeated installation and additional code checkouts reuse the same 3.14 environment by default.

Before rerunning the installer or pulling code updates, close workbench browser tabs/notebooks and stop their launchers. The installer uses `requirements.txt`, retains already-compatible packages (no blanket upgrade), checks dependency consistency, and registers the **Tensile Workbench** kernel inside that environment. Rerun the installer if the app reports a missing/incompatible dependency. Built-in updates handle dependency changes automatically.

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

- **Missing Python:** run the app installer and accept its Python offer, or install the supported Python version above manually and rerun the app installer. Both systems check the selected environment and standard installation locations. Windows also checks the Python launcher and PATH; Mac also checks Python.org and Homebrew. Cancellation stops installation without repeatedly prompting.
- **Windows shortcut does not open:** double-click `Launch_Tensile_Workbench_App.bat` for visible startup errors. Check that the code folder and Python environment still exist, then rerun the app installer. If the control window opens but the server stops, use **View log**. A missing Tcl/Tk component requires modifying the Python installation, not installing a pip package.
- **Mac command file permission:** if the downloaded ZIP lost executable permissions, open Terminal, type `/bin/zsh `, drag `Install_Tensile_Workbench_App.command` into the window, then press Return. Use the same approach for Launch. If macOS blocks the download with a security warning, review it through the normal macOS approval workflow or ask IT; do not disable Gatekeeper.
- **Mac Dock app was not installed:** follow the build-tool message above, quit any running Dock app and run Install_Tensile_Workbench_App.command again. A broken or unrecognised app at the destination is not overwritten; preserve or move it deliberately before retrying. Installation prepares the environment and launcher without starting the server.
- **Network/package failure:** retry the app installer when network access is restored. Packages are installed without a persistent pip download cache; setup uses binary wheels and will report an error instead of starting a lengthy source build. Do not disable certificate verification. For Python.org certificate errors on Mac, follow the Python installer's certificate instructions or ask IT.
- **Partial installation:** if the environment's Python exists, the installer can retry missing packages. If the interpreter is missing/broken but the directory contains files, it stops instead of overwriting them. Close all workbench sessions; rename that **specific environment folder** as a backup and rerun the app installer. Keep the backup until the replacement works; do not rename/delete research folders.
- **App fails to load / missing kernel:** close the app, rerun its installer and open it again. The app runs automatically through Voilà using the environment's `python3` kernel. Users do not need to choose a kernel. Advanced notebook access is still available with `python launch_workbench.py --notebook`; in that mode select **Tensile Workbench** and Run All Cells. Kernel registration uses `--sys-prefix`, not a global user kernel. See [IPython's kernel documentation](https://ipython.readthedocs.io/en/stable/install/kernel_install.html).
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
