# Tensile Workbench

Analyse tensile-test CSV exports in a local browser app. Compare sample groups, review individual specimens, produce publication plots and export results to Excel. **No Jupyter or programming knowledge is needed for normal use.**

The workbench includes stress–strain curves, work-hardening plots, strength–elongation comparisons, specimen statistics and comparisons with available Instron summary CSVs. Three small synthetic datasets let you try it before adding your own data.

Use **Analysis** for graphs and specimen review. **Saved specimen overrides** lists manual fits, failure endpoints and data-use/exclusion settings across all your specimens and saved graphs. Tick rows to disable, re-enable or remove settings; you do not need to select those groups in the current graph.

## 1. Install and launch

You need **standard Python 3.13, 64-bit**, a browser, and internet access during setup. Setup scripts support Windows x86-64 and macOS (Apple Silicon or Intel). If Python is not installed, follow the platform-specific links in [SETUP.md](SETUP.md#first-use).

1. Download the repository ZIP and **extract it completely**, or clone the repository. Put the application in a writable folder.
2. Double-click the **Setup** file for your system. Wait for **Setup complete**.
3. Open the launcher for your system to start the app in your browser.

| System | First installation | Open the app afterwards |
|---|---|---|
| Windows | [Setup_Tensile_Workbench.bat](Setup_Tensile_Workbench.bat) | [Launch_Tensile_Workbench.bat](Launch_Tensile_Workbench.bat) |
| macOS | [Setup_Tensile_Workbench.command](Setup_Tensile_Workbench.command) | **Tensile Workbench.app** in your user Applications folder; or [Launch_Tensile_Workbench.command](Launch_Tensile_Workbench.command) |

Setup creates or reuses a separate local Python environment outside the code and data folders. It installs dependencies but does not analyse data. Launch reuses that environment and does not install packages.

**Mac Dock app:** on macOS 13 or newer, Setup also builds a small native launcher in **~/Applications/Tensile Workbench.app**. This requires Apple's Command Line Tools (or Xcode); if missing, Setup explains how to install them. Drag the app to your Dock. It stays open, runs the server without Terminal, and offers **Open Workbench**, **Start/Stop** and **View log** (live updates, auto-scroll and copying). Closing its window leaves the server running; **Quit** stops the server it started. It does not stop an existing Terminal-launched server—stop that with Ctrl-C before switching.

**Windows and Mac Terminal launcher:** leave the launcher's terminal window open while working. To stop the app, return to it and press **Ctrl-C**. If the browser does not open, use **Open Workbench** in the Dock app or copy the complete URL printed in the terminal, including its token. There is no notebook to select and no cell to run.

See [SETUP.md](SETUP.md) for detailed installation, environment locations and troubleshooting.

## 2. Choose folders—or try the examples

On first launch, confirm the **Data folder** and **Output folder**, then click **Save folders and open**.

- Defaults are **./data** and **./output**, relative to the application folder.
- Either folder can be elsewhere on your computer or on an accessible external/network drive.
- Changing these settings never moves or copies existing data.
- Change them later under **Folders · data and output locations**.

To explore first, leave **Show sample data** enabled and select **Demo comparison**. The examples appear alongside your own groups without changing your data folder. They are invented curves, not experimental results. See [examples/README.md](examples/README.md).

### Add your own data

Use one folder per sample group, with one raw curve CSV per specimen. Groups can sit directly in the data folder or inside **any number of organisational folders** (colleague, project, material, etc.). Use descriptive names that suit your experiments.

    data/
    ├── As built/
    │   ├── specimen_1.csv
    │   ├── specimen_2.csv
    │   └── summary.csv
    ├── Heat treated/
    │   └── instrument_exports/
    │       ├── specimen_1.csv
    │       └── specimen_2.csv
    └── Guofang/
        └── Project A/
            └── Batch 1/
                ├── Sample X/
                │   ├── specimen_A.csv
                │   └── specimen_B.csv
                └── Sample Y/
                    └── specimen_A.csv

In **Sample groups**, tick a folder to select all groups below it. Expand it with the arrow to select individual groups or subfolders; a mixed checkbox shows partial selection. Selecting a folder does **not** pool its groups into one average. Graph definitions save the selected groups, so newly added groups are not silently added to existing graphs.

Keep organisational folders as containers of other folders. A folder containing CSVs, an Instron `.is_tens`/`.id_tens` file, or an export subfolder (such as `instrument_exports` or `*.is_tens_Exports`) is treated as a sample group; its nested exports belong to that group. Keep summary CSVs inside their sample group, not in a parent organisational folder.

Nested export folders are supported. Keep original CSV headings and units; the reader recognises supported stress/strain columns and skips summary headers before the time-series data. Available Instron summary CSVs can remain with their dataset for comparison. PDF reports are not imported.

Keep original export filenames where possible: names and export row numbers help associate curves with summary rows. A **!** anywhere in a file or nested folder name makes the workbench ignore it entirely. For routine exclusions, use the **Data use** dropdown instead.

After adding or changing files, click **Reload data**. Cloud-hosted files must be downloaded and accessible locally.

Group identities include their relative folder path, so different colleagues can use the same sample names without their data being merged. Existing flat layouts still work.

**Moving groups:** open this version once before reorganising existing data, so it can remember file fingerprints for groups with saved selections/settings. After moving folders, use **Reload data** or **Check for moved groups**. Each verified move is flagged beside the selector with its old/new paths and a separate **OK, migrate settings** button. Approving it carries saved graph selections, specimen overrides/exclusions and group settings to the new location; nothing transfers without your OK. The workbench does not move source files itself. Ambiguous duplicates or conflicting settings are blocked. See [move protection](WORKBENCH_GUIDE.md#moving-data-and-retaining-settings) for limitations.

## 3. Everyday workflow

1. **Choose a graph definition.** Select an existing graph, duplicate one, or choose **＋ Create new graph…**. Give it a useful name and tick the exact sample groups. Changes save automatically.
2. **Review the data.** Expand **Specimen properties · tables and calculation inspector**. Summary shows group statistics; Specimens shows individual results and check messages. Click a specimen name to inspect its curve, elastic fit and fracture endpoint.
3. **Resolve questionable results.** Use **Group curve review** to overlay one group's raw specimen curves. Preview and save manual yield-fit or failure-elongation overrides in the inspector when needed. Use **Data use** to exclude an entire specimen or only properties affected by AVE failure. Exclusions are global unless you explicitly select a graph-only exception. Original data files are not altered.
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
| YS/UTS/EL by sample group & custom variable | Comparing group means by name or against a numeric variable, with multiple chart variants |
| YS/UTS/EL by specimen | One chart per group, comparing individual properties against Location or another specimen variable |

In either YS/UTS/EL section, **Settings → Add chart variant** creates another independently configured chart within the saved graph. Select **Edit chart** to configure its title, X-axis, property switches, colours and axis limits. Group charts also offer connecting lines (**Straight / solid**, **Dash**, **Dot**, **None**) and SD bars. Specimen charts use grouped bars with trendlines and create one figure per chosen group. All variants render and export together. An EL-only chart uses a single axis; with strength enabled, EL uses the right axis. Adding a variant copies its settings; removing it leaves the others untouched.

To plot against a numeric variable, such as shielding-gas CO₂ concentration:

1. Select sample groups, then expand **Custom variables → Sample groups** below the sample selector/order controls.
2. Select **New variable…**, then enter a name, optional units and each group's value. Leave unknown values blank; `0` is a real value. **Show all sample groups** lets you edit groups outside the current selection. The permanent **Specimen count** variable is described below.
3. Click **Save variable and values**. Or choose **View → Table** to edit all variables together: names in row 1, units in row 2, then sample-group data. **Add variable (column)** creates another column; **Save all variables** applies the complete table. Variables are shared across saved graphs.
4. In the property chart's **Settings**, choose the variable under **X-axis**, switch the desired properties on/off, then **Update plots**. Add more chart variants to compare other variables or property combinations.

Numeric X values use their actual spacing in ascending order. Groups with missing values are flagged and omitted from that chart only; groups sharing an X value remain separate, not pooled. Lines connect means, not fitted trends. Statistics, eligibility and ±1 sample SD bars follow the existing property calculations. With **Sample names** as the X-axis, the shared **Sample group order** applies; **X-axis labels · this plot only** provides short labels without renaming groups elsewhere.

In table view, paste a rectangular block from Excel, CSV or TSV into its starting cell. Paste variable cells only, without sample-group labels; rows follow the visible group order. Extra variable columns are added automatically, but pastes cannot extend beyond the visible groups. Blank cells clear values, while `0` remains a value. Invalid blocks are rejected without partial changes. **Copy variable cells (TSV)** copies names, units and visible values back to a spreadsheet. Save before changing graphs; switching editor views preserves drafts.

To delete a custom variable, select it in **One variable** view and click **Delete variable**, or click **×** beside its name in the table. Review the confirmation and affected chart list, then **Confirm delete**. This removes the variable and all its values globally, without saving or discarding edits to other variables. Charts that used it need a new X-axis selection; they are not silently changed to sample names. Removing an unsaved column only discards its draft. **Specimen count** and **Location** are permanent: their names/units cannot be edited and they cannot be deleted.

For variable-based charts, leave **Title** empty to use the grey automatic title, e.g. **YS/UTS/EL vs. Shielding CO₂ (%)**. It follows the selected variable, units and enabled properties; a typed title overrides it. Numeric subscript/superscript shorthand is formatted in these chart titles and variable-axis labels: `CO_2` → CO₂, `mm^2` → mm², `m^{-3}` → m⁻³. Saved variable text is unchanged; Unicode characters can also be entered directly.

Variables and chart variants are stored in the ignored personal project file, not deployed to colleagues. Values follow an approved sample-folder move. Exports include the chart settings and variable values; table exports add a numeric **Group variables** sheet when variables exist.

To check properties against **specimen extraction location**, enable the separate **YS/UTS/EL by specimen** section:

- Each chosen group gets its own grouped bar chart with a simple YS/UTS/EL legend: strength on the left axis and EL on the right. It does not create duplicate with/without-individuals versions. In **Settings**, use **All sample groups** to select/clear the workspace groups, or tick groups individually. This choice is saved per chart variant and only controls which location charts appear; it does not change the workspace selection, property tables or specimen exclusions.
- **Location** is the default X-axis and a permanent specimen variable. It uses the operator's specimen number, not the CSV export row: `Wall_04` plots at 4. In **Custom variables → Individual specimens**, enter a whole-number override or clear a cell to restore its default. Missing or ambiguous numbers remain blank until you supply a location. Numbers display without decimals. You can also create separate custom variables such as extraction height (mm).
- **Specimen count**, under **Custom variables → Sample groups** near the top, is a permanent whole-number variable for the total tested + untested in each group. Startup and **Reload data** raise a missing or too-small value to the imported specimen count, including excluded specimens. Larger totals are preserved. For example, set 10 when seven of ten coupons have been tested: Location charts retain positions 1–10. Only tested, eligible values receive bars; missing positions are not renumbered, replaced with zero or included in statistics. Custom physical-unit axes use their own values and limits, not the specimen-count range.
- **Quadratic · order 2** trendlines are the default; choose **Linear** or **None** if preferred. A quadratic needs at least three distinct measured locations. Fits use actual locations, not the small offsets used to place bars beside each other. Dashed segments cover the measured range; dotted segments extend to the full count range (or manual X-axis limits). These are descriptive fits, not validated predictions. Each property fits its own eligible observations; insufficient distinct locations leave that trend undrawn.
- YS/UTS/EL switches, manual overrides and partial exclusions still apply. There are no group means or SD bars. Equal locations remain separate observations; no lines connect different groups.

Specimen variables use stable identities, so display-label changes do not reassign them. Approved moves migrate overrides and counts; forgetting a group clears its values. Excel results include effective Location values in **Specimen variables** and totals in **Group variables**, with no fake specimen rows. Existing trial specimen charts migrate to their separate section; saved Location values are retained. Legacy fractional/unit-based locations stay available as a custom variable instead of being rounded away.

The variable editor reads a cached name/header catalogue, not every full curve. **Show all individual specimens** includes unselected groups without recalculating their tests. The single-variable editor pages through 100 specimens at a time; table view supports all rows, editing and CSV/TSV paste. Reload data refreshes the catalogue and automatic locations.

Under **Summary**, the collapsible **Calc–Instron comparison** shows paired percentage differences and separate SD comparisons where both sources are available. UTS discrepancies are reported as specimen checks instead of comparison charts.

### Control property and curve contributions

The **Data use** dropdown is available in Specimens and Group curve review:

| Mode | Properties retained | Curve contributions |
|---|---|---|
| Use all data | All available properties | All eligible curves |
| Exclude from shape | All available properties, including EL and toughness | None; measured curve remains reviewable |
| AVE failed after UTS / Broke outside dots | YS, UTS, fitted E and uniform EL | Pre-peak work hardening only |
| AVE failed after yield, before UTS | YS, UTS and fitted E | None |
| AVE unreliable throughout | UTS only, if the stress record is sound | None |
| Exclude specimen entirely | None | None |

Retaining YS requires reliable strain through the **0.2% offset intersection**, not just through the elastic fit. All partial AVE-failure modes exclude failure EL, reconstructed EL, full-test toughness and full tensile shape. They also exclude the corresponding imported Instron properties from statistics. Original values remain visible (crossed out) and auditable in exports.

Landmark curves use trusted curves for **shape**, then pass through each property's **eligible group mean**. Strength and elongation can therefore use different specimen counts. Pointwise averages use only eligible full curves. Strength–EL scatter plots default to **All eligible values per property** for group means and SDs, matching the summary. Individual dots still require valid pairs. Each scatter plot's **Settings → Group means** also offers **Paired specimens only**; this can give different means from the summary. An on-screen warning lists partial exclusions; warnings are not added to publication plots.

In Group curve review, click a curve or specimen name to highlight it, then use **Inspect highlighted specimen** for detailed checks. Clicking a name never hides or excludes it: change **Data use** in the table below for exclusions. Exclusions have distinct line styles and short labels beside each specimen above the plot.

- **Measured** shows untrimmed measured data even if fracture detection or reconstruction fails. Toggle **YS**, **UTS** and **EL** markers independently; these are measured Calc values, including manual overrides. Excluded properties have hollow markers; unavailable values are omitted. A time-axis option helps when recorded strain itself is unreliable.
- **Landmark-aligned** shows the transformed shape contributions in colour and their landmark average in black, using the current graph's settings. Group-mean YS/UTS/EL markers start enabled. The display reports shape and property counts; property-only specimens stay listed without an invented curve. These are diagnostic synthetic curves, not additional measurements.

Use **Exclude from shape** when the curve shape is unsuitable but its property values are sound. It removes the specimen from tensile/work-hardening curve contributions and representative selection, while retaining its valid properties in group means, comparisons and strength–EL scatter plots. It is global by default, with the same graph-only override as other data-use modes. Use an AVE-failure mode instead when strain-derived properties are unreliable; **Broke outside dots** assumes reliable strain through UTS.

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

The first two files are ignored by Git. They are saved automatically, with backup history **outside the application folder**. A fresh download does not include your personal settings, research data or results. To share a project, provide the personal project file and corresponding data deliberately; choose data/output paths again on the other computer.

### Automatic backups and recovery

Open **Backups & restore**, just below Folders. It lists dated snapshots, with graph counts and revision numbers for project settings. **Back up now** makes a protected copy of both saved settings files. Unsaved editor drafts, research CSVs and exported results are not part of these backups.

- Automatic history retains the latest **20 changed versions** and **30 daily checkpoints**, per settings file. Manual copies and safety copies made before a settings upgrade or restore are retained without automatic expiry.
- Choose **Project** or **Folders**, select a snapshot, then **Restore selected… → Confirm restore**. Only that settings file is restored. The current file is preserved first, even if damaged, and the workbench reopens. Cancel changes nothing.
- A missing or damaged project opens recovery controls instead of silently replacing your graphs with starter definitions. The older `.project.previous.json` copy is also offered when usable. Restored folder paths that are unavailable require you to confirm new locations.
- If backup storage is unavailable, ordinary settings saves continue with a visible warning. Upgrades and restores stop if their required safety copy cannot be made. Another open session must reload before editing restored project settings.

Default backup locations:

| Platform | Location |
|---|---|
| macOS | `~/Library/Application Support/Tensile Workbench/backups/` |
| Windows | `%LOCALAPPDATA%/Tensile Workbench/backups/` |

The panel shows the exact folder for this installation. History is separated by the application folder's path; updating in place keeps it available. Moving the application folder leaves its old history in the old installation's backup subfolder. For an advanced/custom location, set `TENSILE_WORKBENCH_BACKUP_DIR` before launching.

History begins when this version is first launched; it cannot recover older changes that were never backed up. These are local backups, not protection against loss of the computer. Include your settings, backup folder, research data and outputs in your usual off-device backup.

To update:

1. Use **Back up now**, then close the app and stop its launcher. Keep an additional off-device copy of important settings.
2. Pull the new code, or copy the extracted ZIP contents over the existing application folder. **Do not delete the old folder first**; preserve local settings, data and outputs.
3. Rerun Setup if dependencies changed or Launch reports missing packages. On Mac, run [Install_Tensile_Workbench_App.command](Install_Tensile_Workbench_App.command) to rebuild/update the Dock app without reinstalling packages; Setup also does this. Then launch again.

The Mac app points to the checkout/downloaded folder it was built from; it does not contain another copy of the workbench or Python. If you move that folder, rerun **Install_Tensile_Workbench_App.command** from its new location. The launcher source and icon are shared in Git, but installed app bundles, logs, environments and machine-specific paths are not.

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
