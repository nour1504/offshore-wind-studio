"""Wind given as speed and direction, or as earth-relative components, paired on time stamps."""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from owstudio.core.analysis.common import (
    AnalysisError,
    Selection,
    aligned,
    check_same_timing,
    direction_values,
    in_unit,
    speed_values,
)
from owstudio.core.i18n import tr
from owstudio.core.series import Series, circular


def same_place(a: Series, b: Series) -> list[str]:
    """Notes when two series meant to describe one wind come from different places or heights."""
    notes = []
    if (a.meta.dataset, a.meta.location) != (b.meta.dataset, b.meta.location):
        notes.append(
            tr(
                f"{a.meta.key} and {b.meta.key} come from different datasets or locations",
                f"{a.meta.key} et {b.meta.key} viennent de jeux de données ou de lieux différents",
            )
        )
    if (a.meta.height_m, a.meta.height_ref) != (b.meta.height_m, b.meta.height_ref):
        notes.append(
            tr(
                f"{a.meta.key} and {b.meta.key} are at different heights",
                f"{a.meta.key} et {b.meta.key} sont à des hauteurs différentes",
            )
        )
    return notes


@dataclass
class Wind:
    """One wind record: a speed series and, optionally, the matching direction series."""

    speed: Series
    direction: Series | None = None

    def __post_init__(self) -> None:
        if self.direction is not None:
            check_same_timing([self.speed, self.direction], "Wind speed and direction")

    @classmethod
    def from_components(cls, u: Series, v: Series) -> "Wind":
        """Speed and meteorological direction of earth-relative u (eastward) and v (northward)."""
        if u.meta.variable != "u" or v.meta.variable != "v":
            raise AnalysisError(
                tr(
                    f"Wind components must be the variables 'u' and 'v' (earth-relative), not "
                    f"{u.meta.variable!r} and {v.meta.variable!r}",
                    f"Les composantes du vent doivent être les variables 'u' et 'v' (repère terrestre), pas {u.meta.variable!r} et {v.meta.variable!r}",
                )
            )
        check_same_timing([u, v], "Wind components")
        if (u.meta.height_m, u.meta.height_ref, u.meta.location, u.meta.dataset) != (
            v.meta.height_m,
            v.meta.height_ref,
            v.meta.location,
            v.meta.dataset,
        ):
            raise AnalysisError(
                tr(
                    f"{u.meta.key} and {v.meta.key} are not the components of the same wind (same "
                    "dataset, location and height needed)",
                    f"{u.meta.key} et {v.meta.key} ne sont pas les composantes du même vent (même jeu de données, même lieu et même hauteur nécessaires)",
                )
            )
        # All values are kept: their quality flags travel with the derived series
        frame = aligned(
            {
                "u": in_unit(u, u.values, "m s-1", "a wind component"),
                "v": in_unit(v, v.values, "m s-1", "a wind component"),
            }
        )
        uu, vv = frame["u"].to_numpy(), frame["v"].to_numpy()
        flags = list(dict.fromkeys([*u.meta.flags, *v.meta.flags]))
        speed_flags = list(flags)
        if u.meta.averaging_s > 0:
            speed_flags.append(
                "speed of the averaged wind vector, lower than the average of the "
                "instantaneous speeds"
            )
        quality = None
        if u.quality is not None or v.quality is not None:
            parts = [q.reindex(frame.index) for q in (u.quality, v.quality) if q is not None]
            quality = pd.concat(parts, axis=1).max(axis=1).astype("int8")
        method = tr(
            f"derived: from {u.meta.key} and {v.meta.key}",
            f"dérivé : de {u.meta.key} et {v.meta.key}",
        )
        speed = Series(
            u.meta.model_copy(
                update={
                    "variable": "wind_speed",
                    "unit": "m s-1",
                    "source": "derived",
                    "method": method,
                    "flags": speed_flags,
                }
            ),
            pd.Series(np.hypot(uu, vv), index=frame.index),
            quality,
        )
        direction = Series(
            u.meta.model_copy(
                update={
                    "variable": "wind_direction",
                    "unit": "deg",
                    "source": "derived",
                    "method": method,
                    "flags": flags,
                }
            ),
            pd.Series(circular.from_components(uu, vv), index=frame.index),
            None if quality is None else quality.copy(),
        )
        return cls(speed, direction)

    @property
    def key(self) -> str:
        return self.speed.meta.key

    @property
    def series(self) -> list[Series]:
        return [self.speed] if self.direction is None else [self.speed, self.direction]

    def notes(self) -> list[str]:
        return [] if self.direction is None else same_place(self.speed, self.direction)

    def frame(self, selection: Selection, need_direction: bool = False) -> pd.DataFrame:
        """Columns ``speed`` (m s-1) and ``direction`` (degrees, NaN without directions) on the
        time stamps common to both series."""
        speed = speed_values(self.speed, selection)
        if self.direction is None:
            if need_direction:
                raise AnalysisError(
                    tr(
                        f"{self.speed.meta.key}: a wind direction series is needed",
                        f"{self.speed.meta.key} : une série de direction du vent est nécessaire",
                    )
                )
            return pd.DataFrame({"speed": speed, "direction": np.nan}, index=speed.index)
        return aligned({"speed": speed, "direction": direction_values(self.direction, selection)})
