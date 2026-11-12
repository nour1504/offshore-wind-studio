"""Keep GUI period edits authoritative without discarding unrelated imported options."""

from typing import Any

from owstudio.core.case.model import Case

WRF_DATES = {
    f"{which}_{part}"
    for which in ("start", "end")
    for part in ("year", "month", "day", "hour", "minute", "second")
} | {"run_days", "run_hours", "run_minutes", "run_seconds"}
WPS_DATES = {"start_date", "end_date"}


def clear_metadata(options: dict[str, Any], names: set[str]) -> None:
    """Remove indexing/type metadata only for values that are about to be regenerated."""
    for key in list(options):
        value = options[key]
        if key.lower() in ("_start_index", "_complex") and isinstance(value, dict):
            for name in list(value):
                if name.lower() in names:
                    del value[name]
            if not value:
                del options[key]


def _options(groups: dict[str, dict[str, Any]], group_name: str) -> dict[str, Any]:
    return {
        key.lower(): value
        for group, options in groups.items()
        if group.lower() == group_name
        for key, value in options.items()
    }


def _clear_unchanged(
    previous: dict[str, dict[str, Any]],
    next_groups: dict[str, dict[str, Any]],
    group_name: str,
    names: set[str],
) -> None:
    old = _options(previous, group_name)
    for group in list(next_groups):
        if group.lower() != group_name:
            continue
        options = next_groups[group]
        cleared: set[str] = set()
        for key in list(options):
            name = key.lower()
            if name in names and name in old and options[key] == old[name]:
                del options[key]
                cleared.add(name)
        clear_metadata(options, cleared)
        if not options:
            del next_groups[group]


def synchronize_period(previous: Case, next_case: Case) -> None:
    """Reset stale retained overrides on save; newly supplied import values stay explicit.

    The frontend clears all managed date overrides on a GUI period edit. This also protects
    API clients that update the period while returning the unchanged imported namelists.
    """
    if (
        previous.period.start != next_case.period.start
        or previous.period.end != next_case.period.end
    ):
        _clear_unchanged(
            previous.namelist_input, next_case.namelist_input, "time_control", WRF_DATES
        )
        _clear_unchanged(previous.namelist_wps, next_case.namelist_wps, "share", WPS_DATES)
    if previous.period.interval_seconds != next_case.period.interval_seconds:
        names = {"interval_seconds"}
        _clear_unchanged(previous.namelist_input, next_case.namelist_input, "time_control", names)
        _clear_unchanged(previous.namelist_wps, next_case.namelist_wps, "share", names)
