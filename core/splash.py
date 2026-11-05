"""Closing the start-up splash screen.

The portable .exe unpacks itself every time it starts, which takes a few
seconds. The packaging tool shows a splash picture during that wait, and the
app has to tell it when to go away.

All of that lives in this one file on purpose: each packaging tool has its own
way of signalling it, so switching tools later (for example to the Nuitka
compiler) means changing close_splash() here and the build script, and nothing
else in the app.

Today: PyInstaller, through its pyi_splash module.
When running from source there is no splash, and nothing happens.
"""


def close_splash() -> None:
    """Close the splash screen if there is one. Safe to call at any time."""
    try:
        import pyi_splash  # only exists in a PyInstaller build made with --splash
    except ImportError:
        return
    try:
        pyi_splash.close()
    except Exception:
        # The splash is cosmetic. Whatever goes wrong with it, the app must still start.
        pass
