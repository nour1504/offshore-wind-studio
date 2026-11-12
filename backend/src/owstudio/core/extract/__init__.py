"""Series and maps from WRF outputs (history files and tslist), in the common series format.

Importing the package registers the resolver of series references of kind "run"."""

from owstudio.core.extract import runs as _runs  # noqa: F401  (registers the "run" resolver)
