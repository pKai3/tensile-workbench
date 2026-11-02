"""Regenerate the checked-in ICO from the shared Mac icon (developer tool only)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    from PIL import Image
    destination = ROOT / 'windows/TensileWorkbench.ico'
    destination.parent.mkdir(exist_ok=True)
    with Image.open(ROOT / 'macos/TensileWorkbench.icns') as icon:
        icon.convert('RGBA').save(destination, format='ICO',
                                  sizes=[(n, n) for n in (16, 24, 32, 48, 64, 128, 256)])
    print(destination)


if __name__ == '__main__':
    main()
