"""References to series, resolved by the module that knows how to read them.

The interface asks for analyses on series from different places (a run's wrfout or tslist
files, an observation dataset, a derived series...). A :class:`SeriesRef` names one series;
each reading module registers a resolver for its ``kind``, so that analyses and comparisons
never depend on where a series comes from.

    register("observation", resolve_observation)
    series = resolve(context, SeriesRef(kind="observation", dataset="fino3", location="mast",
                                        variable="wind_speed", height_m=100))
"""

from collections.abc import Callable
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from owstudio.core.i18n import tr
from owstudio.core.series import HeightRef, Series


class SeriesRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # "run" (simulation outputs), "observation", or any kind registered by a module
    kind: str = Field(min_length=1)
    variable: str = Field(min_length=1)
    # Simulation: case, run ("" for the latest with results), "main" or "control" outputs,
    # domain, and how outputs are read ("tslist" or "wrfout")
    case_id: str = ""
    run_id: str = ""
    stage: Literal["main", "control"] = "main"
    domain: int | None = None
    reader: str = ""
    # Observation dataset, or any other named collection
    dataset: str = ""
    # Location id: tslist prefix, turbine label, observation station; or coordinates
    location: str = ""
    lat: float | None = None
    lon: float | None = None
    height_m: float | None = None
    height_ref: HeightRef = "agl"
    # Free options understood by the resolver: interpolation method, averaging...
    options: dict[str, Any] = Field(default_factory=dict)


class Context(Protocol):
    """What resolvers may use: the application's storage and workspace (AppState satisfies it)."""

    @property
    def storage(self) -> Any: ...

    @property
    def workspace(self) -> Any: ...


Resolver = Callable[[Context, SeriesRef], Series]

_RESOLVERS: dict[str, Resolver] = {}


class SeriesNotFound(LookupError):
    """The reference names nothing that exists; the message says what is missing."""


def register(kind: str, resolver: Resolver) -> None:
    _RESOLVERS[kind] = resolver


def kinds() -> list[str]:
    return sorted(_RESOLVERS)


def resolve(context: Context, ref: SeriesRef) -> Series:
    """The series named by ``ref``. Raises SeriesNotFound when it does not exist."""
    resolver = _RESOLVERS.get(ref.kind)
    if resolver is None:
        raise SeriesNotFound(
            tr(
                f"No reader for series of kind {ref.kind!r} (known: {', '.join(kinds()) or 'none'})",
                f"Aucun lecteur pour les séries de type {ref.kind!r} (connus : {', '.join(kinds()) or 'aucun'})",
            )
        )
    return resolver(context, ref)
