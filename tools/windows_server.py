"""Private desktop-server child. Do not launch this script directly."""
from pathlib import Path
import json
import os
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = 'TENSILE_DESKTOP '


def notify(**values):
    # The owning launcher consumes these records from its private stdout pipe;
    # URL/token records never enter the user-visible log.
    print(PROTOCOL + json.dumps(values), flush=True)


def watch_control(stream, loop):
    for line in stream:
        if line.strip() == 'stop':
            break
    loop.add_callback(loop.stop)  # EOF means the control window has gone away.


def server_arguments(root, token):
    # Voilà sets the identity provider's token from Voila.token. Setting only
    # IdentityProvider.token would be overwritten (and authentication disabled).
    return [
        str(root / 'workbench_app.py'), '--Voila.ip=127.0.0.1', '--Voila.port=8866',
        '--Voila.open_browser=True', '--Voila.base_url=/', '--Voila.token=' + token,
        '--VoilaConfiguration.extension_language_mapping=.py=python',
        '--VoilaConfiguration.language_kernel_mapping=python=python3',
        '--MappingKernelManager.cull_interval=60', '--MappingKernelManager.cull_idle_timeout=1800',
        '--MappingKernelManager.cull_connected=False',
    ]


def main():
    # No imports that can create children before the parent assigns our job.
    if sys.stdin.readline().strip() != 'start':
        return 1
    sys.path.insert(0, str(ROOT))
    from workbench_environment import (check_project_files, require_runtime,
                                       validate_environment_location, verify)
    folder = Path(sys.prefix).resolve()
    require_runtime()
    validate_environment_location(folder, ROOT)
    check_project_files(ROOT)
    if sys.prefix == sys.base_prefix:
        raise RuntimeError('Run the installed Workbench environment, not system Python.')
    notify(phase='checking')
    verify(Path(sys.executable), ROOT, os.environ.copy(), full=False)
    notify(phase='starting')
    from tornado.ioloop import IOLoop
    from workbench_server import WorkbenchVoila

    class DesktopVoila(WorkbenchVoila):
        def launch_browser(self):
            # Voilà calls this after binding the actual available loopback port.
            notify(phase='ready', url=self.browser_url())
            loop = IOLoop.current()
            threading.Thread(target=watch_control, args=(sys.stdin, loop), daemon=True).start()

    token = os.environ.pop('TENSILE_DESKTOP_TOKEN')
    # An explicitly set token makes Voilà redact its normal startup URL in logs.
    DesktopVoila.launch_instance(argv=server_arguments(ROOT, token))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print('Could not start Tensile Workbench: ' + str(error), file=sys.stderr, flush=True)
        raise SystemExit(1)
