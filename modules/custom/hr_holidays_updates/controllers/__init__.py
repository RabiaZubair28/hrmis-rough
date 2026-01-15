from . import main
try:
    # Optional controller module: keep addon installable even if this import fails
    # due to stale bytecode or partial initialization in some deployments.
    from . import notifications  # noqa: F401
except Exception:
    # Do not fail addon install because a website controller couldn't be imported.
    # (Routes from `main` remain available.)
    notifications = None