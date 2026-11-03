# Tensile Workbench 1.0.1

- One installer and one desktop-app launch file per platform. Removed the
  duplicate Setup files and Windows console launch file from the main folder.
- The Mac installer now prepares Python packages and the desktop launcher
  together, matching Windows. It checks that the app is closed before changing
  packages. The Mac Launch file opens the installed app.
- Normal updates use **Check for updates → Install update and restart** in the
  desktop control window. Console commands remain under `tools` for troubleshooting.
- Installing over an older ZIP retires unchanged duplicate launch scripts and
  backs them up. Customised scripts are preserved. Saved settings and data stay
  in place.

**Already on 1.0.0?** Install this release from the app's **Check for updates**
button. For a first installation, download **Tensile-Workbench-1.0.1.zip**, extract
it and run **Install_Tensile_Workbench_App.bat** (Windows) or
**Install_Tensile_Workbench_App.command** (Mac).
