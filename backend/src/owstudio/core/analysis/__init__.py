"""Wind analyses on series in the common format: roses, Weibull fits, distributions, time
aggregation and cycles, vertical profiles, shear and veer, stability classes and comparisons.

Every analysis takes :class:`owstudio.core.series.Series`, refuses meaningless requests with an
:class:`~owstudio.core.analysis.common.AnalysisError` whose message is shown to the user, and
returns a :class:`~owstudio.core.analysis.common.Result`: chart-ready data, tables offered as
CSV, the method used and the caveats. The methods are described in the help (data/docs/*/analyses.md).
"""

from owstudio.core.analysis.common import AnalysisError, Result, Selection

__all__ = ["AnalysisError", "Result", "Selection"]
