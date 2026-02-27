"""Axis resolution engine package.

Exports the primary public API for the axis resolution engine.

Typical usage::

    from mud_server.axis import AxisEngine, AxisResolutionResult

The :class:`AxisEngine` is instantiated by
:meth:`~mud_server.core.world.World._init_axis_engine` at world startup.
Callers retrieve it via :meth:`~mud_server.core.world.World.get_axis_engine`.
"""

from mud_server.axis.engine import AxisEngine, CharacterNotFoundError
from mud_server.axis.types import AxisResolutionResult

__all__ = ["AxisEngine", "AxisResolutionResult", "CharacterNotFoundError"]
