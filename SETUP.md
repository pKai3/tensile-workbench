# Setup on Windows and Mac

## First use

1. Clone the repository, or download the GitHub ZIP and **extract it completely**. Keep the code in a writable folder; do not run inside the ZIP. Data and output folders can be elsewhere and are chosen in the notebook. GitHub does not include research data.
2. Install standard **Python 3.13, 64-bit** if it is not already installed:
   - **Windows x86-64:** use the [Python.org Windows downloads](https://www.python.org/downloads/windows/) and include the Python launcher. Do not use the embeddable or free-threaded build. This setup does not currently target Windows ARM64.
   - **Mac, Apple Silicon or Intel:** use the Python 3.13 **macOS 64-bit universal2 installer** from [Python.org](https://www.python.org/downloads/macos/). An existing standard Homebrew Python 3.13 also works. Finder's launcher checks normal Python.org and Homebrew locations even if its PATH is limited.
3. Double-click the setup file for your system:

   | System | Setup once / install missing dependencies | Open normally |
   | --- | --- | --- |
   | Windows | `Setup_Tensile_Workbench.bat` | `Launch_Tensile_Workbench.bat` |
   | Mac | `Setup_Tensile_Workbench.command` | `Launch_Tensile_Workbench.command` |

4. Wait for **Setup complete**. Internet access is needed for package installation. Setup checks imports and graph-definition validity but does not load research datasets, create plots, change definitions or start Jupyter.
5. Open the Launch file. In Jupyter open `tensile_workbench.ipynb` and choose **Run → Run All Cells**. Confirm the data/output folders on first use. Leave the launcher console open; Ctrl-C stops the server. The server listens on this computer only (`127.0.0.1`).

Python itself is installed separately, not silently downloaded by these scripts. On a managed computer, ask IT to approve Python/package access if blocked. The scripts do not require changing PowerShell execution policy or disabling security protections.

## Existing installations and updates

**Existing users can try Launch directly.** The original Mac environment and the previous Windows v17 package's environment are reused; downloading the code into another folder does not require another environment.

Before running Setup or pulling code updates, save and close workbench notebooks and stop their launchers. Setup installs from `requirements.txt`, retains already-compatible packages (no blanket upgrade), checks dependency consistency, and registers the **Tensile Workbench** kernel inside that environment. Rerun Setup if Launch reports a missing/incompatible dependency, or an update changes requirements. Launch itself never installs packages.

`requirements-windows.txt` is retained unchanged solely to recognise the legacy Windows environment's directory fingerprint. Both LF and CRLF copies are recognised so ZIP versus Git line endings do not create duplicate environments. New installations use the shared `requirements.txt` on both systems. Exact installed versions are recorded locally in `installed-packages.txt` beside the environment; dependency ranges are not a fully locked reproducible environment.

## Where files go

| Item | Windows | Mac |
| --- | --- | --- |
| New environment | `%LOCALAPPDATA%\TensileWorkbench\venv` | `~/Library/Application Support/Tensile Workbench/venv` |
| Existing environment reused | Original `%LOCALAPPDATA%\TensileWorkbench\v17-py313-<fingerprint>\venv`, if present and no new default environment exists | Same path as above |
| Jupyter/configuration caches | Beside the selected environment | Beside the selected environment |
| Code and graph definitions | Your downloaded/cloned folder | Your downloaded/cloned folder |
| Data and output | Your chosen folders | Your chosen folders |

No environment is created in the repository or OneDrive. Setup also refuses known cloud-storage locations or an environment overlapping the code folder. Do not set a custom environment inside a differently named synced folder; the scripts cannot discover every third-party sync configuration. Environments are local installations, not files to copy between computers. See Python's [virtual-environment documentation](https://docs.python.org/3.13/library/venv.html).

Both systems accept `TENSILE_ENV_DIR` as an **absolute path to the environment itself**, not its parent. Set it in the process launching Setup/Launch whenever using a non-default location. Ordinary users do not need this setting.

## Troubleshooting

- **Missing Python:** install the supported Python version above, then rerun Setup. Windows first tries `py -3.13`, then a compatible `python` on PATH. The Mac launcher first tries the existing workbench environment, then supported system install locations.
- **Mac command file permission:** if the downloaded ZIP lost executable permissions, open Terminal, type `/bin/zsh `, drag the Setup `.command` file into the window, then press Return. Use the same approach for Launch. If macOS blocks the download with a security warning, review it through the normal macOS approval workflow or ask IT; do not disable Gatekeeper.
- **Network/package failure:** retry Setup when network access is restored. Packages are installed without a persistent pip download cache; setup uses binary wheels and will report an error instead of starting a lengthy source build. Do not disable certificate verification. For Python.org certificate errors on Mac, follow the Python installer's certificate instructions or ask IT.
- **Partial installation:** if the environment's Python exists, Setup can retry missing packages. If the interpreter is missing/broken but the directory contains files, the script stops instead of overwriting it. Close all workbench sessions; rename that **specific environment folder** as a backup and rerun Setup. Keep the backup until the replacement works; do not rename/delete research folders.
- **Old or missing notebook kernel:** after Setup, select **Tensile Workbench** in Jupyter, then restart the kernel and Run All Cells. The internal kernel name remains `python3` to match the notebook. Registration uses the selected environment's `--sys-prefix`, not a global user kernel. See [IPython's kernel documentation](https://ipython.readthedocs.io/en/stable/install/kernel_install.html).
- **Cloud-only code:** download the project files locally before launch. The preflight detects macOS cloud-only placeholders where the filesystem exposes them. Data must also be locally accessible when you analyse it.
- **Invalid definitions:** a validation error never resets or overwrites your JSON. Preserve your file and resolve the reported problem or restore an intentional backup.

## Checks without plots

Using Python 3.13 from any working directory:

```text
python /path/to/tensile-workbench/workbench_environment.py check
```

This finds the selected environment and checks dependencies/imports/definitions without installing anything or starting the notebook. Automated tests use temporary synthetic folders and mock installation commands; they do not run pip or analyse research data. Windows-specific path/launch behavior is tested in simulation on Mac; a real Windows installation remains a colleague-side smoke test.
