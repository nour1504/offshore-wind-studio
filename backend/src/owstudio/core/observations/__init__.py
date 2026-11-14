"""Observations (met masts, LiDARs, buoys, research platforms): import with saved mappings,
conversion to the common series format, alignment and comparison with simulations.

Importing the package registers the resolver of series references of kind "observation"."""

from owstudio.core.observations import store as _store  # noqa: F401  (registers the resolver)
