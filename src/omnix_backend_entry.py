"""PyInstaller entry point for the managed OMNI-X desktop backend."""

from omnix.desktop_server import main


if __name__ == "__main__":
    raise SystemExit(main())
