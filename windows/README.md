# Windows desktop launcher

Run **Install_Tensile_Workbench_App.bat** from a complete checkout/ZIP on Windows
10/11 x86-64 with standard Python 3.13, including Tcl/Tk. It sets up or reuses the
external environment, then creates per-user Desktop and Start-menu shortcuts.
See [SETUP.md](../SETUP.md#windows-desktop-app) for user instructions.

The persistent Tk control window follows the TEM Workbench launcher layout:
Start/Stop, Open Workbench and a separate live log. The analytical interface
continues to run in the user's default browser. This does not bundle Python or
duplicate the saved project. The existing console launcher still works.

## Files and lifecycle

- `tools/install_windows_app.py` creates shortcuts through Windows Script Host,
  using PowerShell with paths passed as environment data. It checks Tcl/Tk before
  writing shortcuts, preserves a custom environment, and refuses to overwrite
  unrelated shortcuts with the same name. No execution-policy changes are made.
- `tools/windows_app.py` is launched with the environment's `pythonw.exe`.
  Its single-instance mutex is specific to the code folder. It runs preflight
  and the server in a separate child, keeping the controls responsive.
- `tools/windows_server.py` waits for the parent's start command before imports
  or child creation. It reports the actual bound, authenticated loopback URL
  over a private pipe. The parent opens the browser outside the managed job.
  No server log parsing is needed to guess readiness or the port.
- `tools/windows_process.py` assigns the server to a Windows Job Object with
  `KILL_ON_JOB_CLOSE`. The job owns the server and its kernels. Normal shutdown
  asks the server's event loop to stop, allowing Voilà's kernel cleanup; after
  ten seconds the job is closed. Unexpected launcher exit also closes the job.
  Unrelated Python applications and separately launched workbenches are untouched.
- Logs are outside the checkout, under
  `%LOCALAPPDATA%\TensileWorkbench\logs\<checkout ID>\launcher.log`. Logging
  redacts access tokens and keeps at most two 2 MB files. The live viewer reads
  a bounded 128 KiB tail. Different checkouts use separate logs.
- `TensileWorkbench.ico` contains 16–256 px versions of the existing Workbench
  artwork. Developers can regenerate it from the Mac ICNS using
  `python tools/build_windows_icon.py` with Pillow installed. Users do not need
  that tool to install the app.

## Verification

Controller/installer tests run on either platform with mocked Windows calls.
Server handoff can also be checked against a real Voilà process on Mac using
only temporary synthetic data. Native job/mutex integration tests run on Windows:

```text
python -m unittest tests.test_windows_app tests.test_windows_process
```

Before distributing as a verified Windows release, check on a Windows machine:

1. Install from a folder containing spaces. Confirm Desktop and Start-menu
   shortcuts open the control window with the Workbench icon and no console.
2. Confirm dependency checks finish, the browser authenticates, and the bundled
   examples load. Stop, Start and Open Workbench should work again.
3. Open View log; confirm live updates, scrolling and Copy log. Confirm there
   is no access token in the copied text.
4. Close the browser, then reopen it from the app. Close the control window and
   confirm the server and its kernels exit. An unrelated Python process must
   remain running. Repeat while the app is still starting.
5. Launch the shortcut twice; only one control window should remain. Try with
   the initial web port occupied; Open Workbench should use the next bound port.
6. Verify an unavailable dependency or missing Tcl/Tk gives an actionable error.
   Reinstall shortcuts after moving the code folder and with `TENSILE_ENV_DIR`
   set to a custom external environment. Personal settings must remain intact.

Native Windows UI/shortcut behavior cannot be verified by the Mac test run.
