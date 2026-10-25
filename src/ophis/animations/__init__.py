from .effects import (  # noqa: F401
    ANIMATIONS,
    COLS,
    EFFECTS,
    ROWS,
    Colour,
    Matrix,
    Params,
    Setting,
    blank,
    create,
    default_params,
    fill,
    hue_colour,
    scale,
)

__all__ = [
    "ANIMATIONS",
    "COLS",
    "EFFECTS",
    "ROWS",
    "AnimationEngine",
    "Colour",
    "Matrix",
    "Params",
    "Setting",
    "blank",
    "create",
    "default_params",
    "fill",
    "hue_colour",
    "scale",
]


def __getattr__(name: str):
    """Import the GTK engine only when a caller asks for it.

    The Windows build has no PyGObject, and importing `animations` must stay
    platform-neutral.
    """
    if name == "AnimationEngine":
        from .engine import AnimationEngine

        return AnimationEngine
    raise AttributeError(name)
