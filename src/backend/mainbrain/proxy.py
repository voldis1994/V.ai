"""Saderības tilts: `mainbrain.proxy` → `mainbrain.tools.proxy`.

Vecāki / bojāti `__init__.py` dažkārt dara `from .proxy import ToolProxy`.
Bez šī faila backend krīt ar ModuleNotFoundError un UI rāda «Python backend aizvērās».
"""

from mainbrain.tools.proxy import ToolProxy

__all__ = ["ToolProxy"]
