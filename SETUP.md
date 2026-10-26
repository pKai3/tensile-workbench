# Setup on Windows and Mac

## First use

1. Clone the repository, or download the GitHub ZIP and **extract it completely**. Keep the code in a writable folder; do not run inside the ZIP. Data and output folders can be elsewhere and are chosen in the app. GitHub does not include research data.
2. Install standard **Python 3.13, 64-bit** if it is not already installed:
   - **Windows x86-64:** use the [Python.org Windows downloads](https://www.python.org/downloads/windows/) and include the Python launcher. Do not use the embeddable or free-threaded build. This setup does not currently target Windows ARM64.
   - **Mac, Apple Silicon or Intel:** use the Python 3.13 **macOS 64-bit universal2 installer** from [Python.org](https://www.python.org/downloads/macos/). An existing standard Homebrew Python 3.13 also works. Finder's launcher checks normal Python.org and Homebrew locations even if its PATH is limited.
3. Double-click the setup file for your system:

   | System | Setup once / install missing dependencies | Open normally |
   | --- | --- | --- |
   | Windows | `Setup_Tensile_Workbench.bat` | `Launch_Tensile_Workbench.bat` |
   | Mac | `Setup_Tensile_Workbench.command` | `Tensile Workbench.app` in your user Applications folder, or `Launch_Tensile_Workbench.command` |

4. Wait for **Setup complete**. Internet access is needed for package installation. Setup checks imports and analysis-definition validity but does not load research datasets, create plots, change definitions or start Jupyter.
5. Open the Dock app on Mac, or the Launch file on either platform. The web app opens in your browser and runs automatically—there is no notebook editor or Run All Cells step. Confirm the data/output folders on first use. With the Terminal/console launcher, leave its window open; Ctrl-C stops the server. With the Dock app, use Stop or Quit. The server listens on this computer only (`127.0.0.1`).

Python itself is installed separately, not silently downloaded by these scripts. On a managed computer, ask IT to approve Python/package access if blocked. The scripts do not require changing PowerShell execution policy or disabling security protections.

## Mac Dock app

The optional native launcher requires **macOS 13 or newer** and **Apple Command Line Tools** (or Xcode). Setup builds it after Python setup succeeds. If the build tools are missing, run `xcode-select --install` in Terminal and complete Apple's installer, then double-click **Install_Tensile_Workbench_App.command**. Full Xcode is not required. This adds a build-tool download; it is not needed if you prefer the existing Terminal launcher. On older macOS, the Dock app is unavailable; use the Terminal launcher if the Python/dependency installation supports your system.

- The app is installed in **~/Applications/Tensile Workbench.app**, without administrator privileges. In Finder, choose Go → Go to Folder and enter `~/Applications`, then drag the app to your Dock.
- **Open Workbench** reopens the browser using the current server's authenticated address.
- **View log** opens a resizable window inside the app, updating twice a second. Untick Auto-scroll to inspect earlier messages; Jump to latest resumes following. Copy log copies the displayed text. The viewer keeps a bounded recent tail; logs may contain a local access token, so check them before sharing.
- Closing the launcher/log window does **not** stop the server. **Stop** or **Quit** asks for confirmation and stops only the server started by this app, allowing its kernels to close. Save work before stopping.
- A server already running from this same checkout in Terminal is not adopted or stopped automatically. Stop it with Ctrl-C, then click Start in the app.
- Quit the Dock app before installing an update. The installer refuses to replace a running launcher. Existing app contents are backed up under **~/Library/Application Support/Tensile Workbench/launcher-backups/**. No source data or personal settings are moved.

The installed app uses your existing checkout and Python environment. It is **not a portable copy of the whole workbench**. Git contains `macos/Launcher.swift`, a generic `macos/Info.plist`, the icon and the installer; installation fills in local paths only in the built app. Build/signing is local (ad-hoc), not an Apple-notarised downloadable binary. Keep normal macOS security protections enabled.

After pulling/unzipping updates, run **Install_Tensile_Workbench_App.command** to update just the launcher; it neither installs packages nor starts the server. Rerunning Setup also updates it. If the checkout moves, rerun the installer from the new location. Apple Silicon and Intel Macs build for their own architecture. Temporary compiler caches are removed after the build, including on failure.

## Existing installations and updates

**Existing users upgrading from notebook-only mode should run Setup once to add Voilà, then use Launch normally.** The original Mac environment and the previous Windows v17 package's environment are reused; downloading the code into another folder does not require another environment.

Before running Setup or pulling code updates, close workbench browser tabs/notebooks and stop their launchers. Setup installs from `requirements.txt`, retains already-compatible packages (no blanket upgrade), checks dependency consistency, and registers the **Tensile Workbench** kernel inside that environment. Rerun Setup if Launch reports a missing/incompatible dependency, or an update changes requirements. Launch itself never installs packages.

Normal Launch checks installed package versions and saved definitions without importing the entire numerical/UI stack twice. Setup and the explicit `check` command below retain the full import checks. Opening the app still starts a Python kernel, loads the selected groups' property tables and, if Live preview is enabled, calculates the saved plot views. Wait for that first load; refreshing starts a new session and repeats this work.

`requirements-windows.txt` is retained unchanged solely to recognise the legacy Windows environment's directory fingerprint. Both LF and CRLF copies are recognised so ZIP versus Git line endings do not create duplicate environments. New installations use the shared `requirements.txt` on both systems. Exact installed versions are recorded locally in `installed-packages.txt` beside the environment; dependency ranges are not a fully locked reproducible environment.

## Where files go

| Item | Windows | Mac |
| --- | --- | --- |
| New environment | `%LOCALAPPDATA%\TensileWorkbench\venv` | `~/Library/Application Support/Tensile Workbench/venv` |
| Existing environment reused | Original `%LOCALAPPDATA%\TensileWorkbench\v17-py313-<fingerprint>\venv`, if present and no new default environment exists | Same path as above |
| Jupyter/configuration caches | Beside the selected environment | Beside the selected environment |
| Code and analysis definitions | Your downloaded/cloned folder | Your downloaded/cloned folder |
| Dock app (optional) | Not applicable | `~/Applications/Tensile Workbench.app` |
| Dock app logs | Not applicable | `~/Library/Logs/Tensile Workbench/launcher.log` (one previous launch retained) |
| Data and output | Your chosen folders | Your chosen folders |

No environment is created in the repository or OneDrive. Setup also refuses known cloud-storage locations or an environment overlapping the code folder. Do not set a custom environment inside a differently named synced folder; the scripts cannot discover every third-party sync configuration. Environments are local installations, not files to copy between computers. See Python's [virtual-environment documentation](https://docs.python.org/3.13/library/venv.html).

Both systems accept `TENSILE_ENV_DIR` as an **absolute path to the environment itself**, not its parent. Set it in the process launching Setup/Launch whenever using a non-default location. On Mac, when set for Setup or Install_Tensile_Workbench_App.command, it is also recorded in the locally built Dock app so Finder launches use the same environment. Rerun that installer with the new value to change it; omit the variable to return the Dock app to the default environment. Ordinary users do not need this setting.

## Troubleshooting

- **Missing Python:** install the supported Python version above, then rerun Setup. Windows first tries `py -3.13`, then a compatible `python` on PATH. The Mac launcher first tries the existing workbench environment, then supported system install locations.
- **Mac command file permission:** if the downloaded ZIP lost executable permissions, open Terminal, type `/bin/zsh `, drag the Setup `.command` file into the window, then press Return. Use the same approach for Launch. If macOS blocks the download with a security warning, review it through the normal macOS approval workflow or ask IT; do not disable Gatekeeper.
- **Mac Dock app was not installed:** Python setup can still succeed. Follow the build-tool message above, quit any running Dock app and run Install_Tensile_Workbench_App.command again. A broken or unrecognised app at the destination is not overwritten; preserve or move it deliberately before retrying. The installer never launches the server or changes your environment.
- **Network/package failure:** retry Setup when network access is restored. Packages are installed without a persistent pip download cache; setup uses binary wheels and will report an error instead of starting a lengthy source build. Do not disable certificate verification. For Python.org certificate errors on Mac, follow the Python installer's certificate instructions or ask IT.
- **Partial installation:** if the environment's Python exists, Setup can retry missing packages. If the interpreter is missing/broken but the directory contains files, the script stops instead of overwriting it. Close all workbench sessions; rename that **specific environment folder** as a backup and rerun Setup. Keep the backup until the replacement works; do not rename/delete research folders.
- **App fails to load / missing kernel:** rerun Setup, then close and reopen Launch. The app runs automatically through Voilà using the environment's `python3` kernel. Users do not need to choose a kernel. Advanced notebook access is still available with `python launch_workbench.py --notebook`; in that mode select **Tensile Workbench** and Run All Cells. Kernel registration uses `--sys-prefix`, not a global user kernel. See [IPython's kernel documentation](https://ipython.readthedocs.io/en/stable/install/kernel_install.html).
- **Cloud-only code:** download the project files locally before launch. The preflight detects macOS cloud-only placeholders where the filesystem exposes them. Data must also be locally accessible when you analyse it.
- **Invalid definitions:** a validation error never resets or overwrites your JSON. Preserve your file and resolve the reported problem or restore an intentional backup.

## Web-app operation

Launch serves the existing widgets using [Voilà](https://voila.readthedocs.io/en/latest/using.html). It binds to `127.0.0.1` and enables a generated login token, which is included in the automatically opened browser URL. If a browser asks for a token, use the URL printed by the launcher. Do not turn authentication off or expose the service directly to the internet.

The small `workbench_server.py` wrapper corrects Voilà 0.5's tokenless browser redirect. It opens the authenticated URL using the actual available port, without changing the installed package or disabling authentication. No setup rerun is needed for this code-only fix. A cleared/expired login-cookie warning can occur after restarting the server; the new token link establishes a fresh login.

Close unused tabs; each page load starts a session. Disconnected idle kernels are cleaned up after 30 minutes. Keep one editing session per project to avoid conflicting saves. Refreshing/reopening restores saved analysis definitions, not temporary plot zoom. Stop and restart Launch after updates. Docker/remote deployment is not included in these local launchers.

## Checks without plots

Using Python 3.13 from any working directory:

```text
python /path/to/tensile-workbench/workbench_environment.py check
```

This finds the selected environment and checks dependencies/imports/definitions without installing anything or starting the web app. Automated tests use temporary synthetic folders and mock installation commands; they do not run pip or analyse research data. Windows-specific path/launch behavior is tested in simulation on Mac; a real Windows installation remains a colleague-side smoke test.
