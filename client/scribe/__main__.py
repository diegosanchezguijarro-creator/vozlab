import sys

from . import DISPLAY_NAME, VERSION

if "--version" in sys.argv:
    print(f"{DISPLAY_NAME} {VERSION}")
    sys.exit(0)

from .app import main  # noqa: E402

if __name__ == "__main__":
    main()
