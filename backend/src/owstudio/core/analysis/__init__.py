"""Wind analyses of series in the common format: roses, Weibull fits, distributions, cycles,
profiles, shear and veer, stability and comparisons.

Each takes :class:`owstudio.core.series.Series`, refuses a meaningless request with an
:class:`~owstudio.core.analysis.common.AnalysisError` shown to the user, and returns a
:class:`~owstudio.core.analysis.common.Result`: chart data, CSV tables, method and caveats
(described in data/docs/*/analyses.md).
"""

from owstudio.core.analysis.common import AnalysisError, Result, Selection

__all__ = ["AnalysisError", "Result", "Selection"]
