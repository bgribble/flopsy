__version__ = "0.0.7"

from .action import Action
from .store import Store
from .reducer import mutates, reducer
from .saga import saga

# Inspector is optional (requires OpenGL, glfw, imgui_bundle, sdl2).
# Import it lazily so 'import flopsy' works without the inspector extras.
__all__ = ["Action", "Store", "mutates", "reducer", "saga", "Inspector"]


def __getattr__(name):
    if name == "Inspector":
        from .inspector.inspector import Inspector
        return Inspector
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
