"""Compatibility entry point for existing Windows shortcuts."""
import sys
from workbench_environment import main as manage_environment


def main():
    if sys.platform != 'win32':
        raise RuntimeError('Use Launch_Tensile_Workbench.command on macOS.')
    return manage_environment(['launch'])


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as error:
        print('\nCould not open Tensile Workbench:', error, file=sys.stderr)
        print('See SETUP.md.', file=sys.stderr)
        raise SystemExit(1)
