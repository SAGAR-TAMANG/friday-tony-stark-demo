"""Entry point wrappers — ensures project root is in sys.path before importing top-level modules."""
import friday  # noqa: F401 — triggers sys.path patch in friday/__init__.py


def run_server():
    from server import main
    main()


def run_voice():
    from agent_friday import dev
    dev()
