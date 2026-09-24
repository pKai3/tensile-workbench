# Tensile Workbench

Analyse tensile-test CSV exports in a local browser app. Compare sample groups, review individual specimens, produce publication plots and export results to Excel. **No Jupyter or programming knowledge is needed for normal use.**

The workbench includes stress–strain curves, work-hardening plots, strength–elongation comparisons, specimen statistics and comparisons with available Instron summary CSVs. Three small synthetic datasets let you try it before adding your own data.

## 1. Install and launch

You need **standard Python 3.13, 64-bit**, a browser, and internet access during setup. Setup scripts support Windows x86-64 and macOS (Apple Silicon or Intel). If Python is not installed, follow the platform-specific links in [SETUP.md](SETUP.md#first-use).

1. Download the repository ZIP and **extract it completely**, or clone the repository. Put the application in a writable folder.
2. Double-click the **Setup** file for your system. Wait for **Setup complete**.
3. Double-click the **Launch** file to open the app in your browser.

| System | First installation | Open the app afterwards |
|---|---|---|
| Windows | [Setup_Tensile_Workbench.bat](Setup_Tensile_Workbench.bat) | [Launch_Tensile_Workbench.bat](Launch_Tensile_Workbench.bat) |
| macOS | [Setup_Tensile_Workbench.command](Setup_Tensile_Workbench.command) | [Launch_Tensile_Workbench.command](Launch_Tensile_Workbench.command) |

Setup creates or reuses a separate local Python environment outside the code and data folders. It installs dependencies but does not analyse data. Launch reuses that environment and does not install packages.

Leave the launcher's terminal window open while working. To stop the app, return to it and press **Ctrl-C**. If the browser does not open, copy the complete URL printed in the terminal, including its token. There is no notebook to select and no cell to run.

See [SETUP.md](SETUP.md) for detailed installation, environment locations and troubleshooting.

## 2. Choose folders—or try the examples

On first launch, confirm the **Data folder** and **Output folder**, then click **Save folders and open**.

- Defaults are **./data** and **./output**, relative to the application folder.
- Either folder can be elsewhere on your computer or on an accessible external/network drive.
- Changing these settings never moves or copies existing data.
- Change them later under **Folders · data and output locations**.

To explore first, leave **Show sample data** enabled and select **Demo comparison**. The examples appear alongside your own groups without changing your data folder. They are invented curves, not experimental results. See [examples/README.md](examples/README.md).

### Add your own data

Use one subfolder per sample group, with one raw curve CSV per specimen. Names do **not** need to follow a B-number format.

    data/
    ├── As built/
    │   ├── specimen_1.csv
    │   ├── specimen_2.csv
    │   └── summary.csv
    └── Heat treated/
        └── instrument_exports/
            ├── specimen_1.csv
            └── specimen_2.csv

Nested export folders are supported. Keep original CSV headings and units; the reader recognises supported stress/strain columns and skips summary headers before the time-series data. Available Instron summary CSVs can remain with their dataset for comparison. PDF reports are not imported.

Keep original export filenames where possible: names and export row numbers help associate curves with summary rows. A **!** anywhere in a file or nested folder name makes the workbench ignore it entirely. For routine exclusions, use the **Include** checkbox instead.

After adding or changing files, click **Reload data**. Cloud-hosted files must be downloaded and accessible locally.

## 3. Everyday workflow

1. **Choose a graph definition.** Select an existing graph, duplicate one, or choose **＋ Create new graph…**. Give it a useful name and tick the exact sample groups. Changes save automatically.
2. **Review the data.** Expand **Specimen properties · tables and calculation inspector**. Summary shows group statistics; Specimens shows individual results and check messages. Click a specimen name to inspect its curve, elastic fit and fracture endpoint.
3. **Resolve questionable results.** Preview and save manual yield-fit or failure-elongation overrides in the inspector when needed. Untick Include to exclude an entire specimen. Exclusions are global unless you explicitly select a graph-only exception. Original data files are not altered.
4. **Choose plots.** Select **Static plots** or **Interactive Plotly**, tick the required plot types, and open their **Settings** for axes and plot-specific options. Choose whether to show individuals or both versions.
5. **Click Update plots.** Live preview is off by default because recalculation can be slow. Set layout and size in the plot-view area. Static plots can be enlarged; Plotly supports zoom, pan and hover.
6. **Export.** Use **Export plot set** for generated views, optionally with Excel tables. Use **Export tables only** when you do not need plots. Outputs go into graph-specific subfolders of your chosen output folder.

### Which view should I choose?

| View | Use it for |
|---|---|
| Landmark / pointwise tensile averages | Comparing group stress–strain responses; the methods combine specimens differently |
| Representative tensile curves | Showing one measured specimen per group, with an optional selection override |
| Work-hardening views | Comparing the pre-necking hardening response |
| YS or UTS vs elongation | Comparing strength and ductility, with optional individual points |
| YS, UTS and elongation by sample | Comparing ordered groups on a dual-axis chart |

For the last view, **Settings** include sample order, connecting lines (**Straight / solid**, **Dash**, **Dot**, **None**), property colours, SD bars and **X-axis labels · this plot only**. Short axis labels here do not shorten names elsewhere.

Under **Summary**, the collapsible **Calc–Instron comparison** shows paired percentage differences and separate SD comparisons where both sources are available. UTS discrepancies are reported as specimen checks instead of comparison charts.

## 4. Understand the results

- **Instron** is an imported summary result; **Calc** is the workbench calculation. Different methods or endpoint definitions can produce different results.
- **Reconstruct** is an optional gauge-length reconstruction, not a directly measured or standards-compliant elongation. Review its formula and assumptions before enabling it.
- Yield strength uses a 0.2% offset fit. Automatic fit and fracture detection can need manual review; check messages and the inspector expose the selections.
- SD bars show specimen scatter, not confidence intervals. Summary comparison error bars specifically show scatter in paired percentage differences.
- Excel retains full numerical precision; ordinary displayed results use two decimals. Fit diagnostics use additional precision.

See the [Workbench Guide](WORKBENCH_GUIDE.md) for methods, overrides, endpoint selection, gauge reconstruction and export definitions.

## 5. Save, back up and update

Your settings are local to the application folder:

| File | Contents |
|---|---|
| tensile_workbench.project.json | Personal graphs, selections, labels and specimen overrides |
| .tensile-paths.json | Data/output locations and sample-data visibility |
| tensile_workbench_defaults.json | Shared starter definitions—not personal settings |

The first two files are ignored by Git. **Back them up separately.** A fresh download does not include your personal settings, research data or results. To share a project, provide the personal project file and corresponding data deliberately; choose data/output paths again on the other computer.

To update:

1. Close the app and stop its launcher. Back up your personal settings.
2. Pull the new code, or copy the extracted ZIP contents over the existing application folder. **Do not delete the old folder first**; preserve local settings, data and outputs.
3. Rerun Setup if dependencies changed or Launch reports missing packages, then Launch again.

For very old installations where personal definitions were tracked by Git, back up **tensile_workbench.project.json** outside the checkout before pulling. That one-time transition can remove the tracked copy; restore your own copy afterwards if necessary.

## Common problems

| Problem | What to try |
|---|---|
| Missing Python or dependencies | Install standard Python 3.13, then rerun Setup |
| Mac will not execute a .command file | See [Mac permission troubleshooting](SETUP.md#troubleshooting) |
| No groups appear | Check the Data folder, group subfolders and local file availability; click Reload data |
| Plots did not change after editing settings | Click Update plots; live preview is normally off |
| Startup or updates are slow | Leave live preview off, select fewer plots, and avoid repeatedly refreshing |
| Browser requests a token | Use the full current URL printed by Launch |
| Settings report a save conflict | Close other sessions editing the same project; retain your settings backup |

The service runs locally on **127.0.0.1**. Keep one editing session per project and do not expose the local server directly to the internet. Advanced setup and optional notebook access are covered in [SETUP.md](SETUP.md) and the [Workbench Guide](WORKBENCH_GUIDE.md#advanced-notebook-mode).

## Licence and copyright

Copyright © 2026 Brogan Csinger, University of Queensland.

Tensile Workbench is licensed under the [MIT License](LICENSE). You may use,
modify and redistribute the software, including commercially, provided the
copyright and permission notice is retained. The software is supplied without
warranty; see the full licence for its terms.

Third-party dependencies retain their own licences. This software licence does
not change the rights applying to datasets you import or results you generate.
