"""The times of the history files are kept in an index next to the outputs: a long run (one file
per instant) is not read file by file again at each opening."""

import json
import os
from pathlib import Path

import numpy as np
import pytest
from test_results import TIMES, wrfout_dataset

from owstudio.core.extract import history
from owstudio.core.extract.history import TIMES_INDEX, HistoryFiles, record_times


def _outputs(folder: Path) -> Path:
    folder.mkdir(parents=True)
    u = np.full((len(TIMES), 4, 5), 8.0)
    wrfout_dataset(u, None).to_netcdf(folder / "wrfout_d01_2025-10-01_00-00-00")
    return folder


def test_times_are_read_once_then_taken_from_the_index(tmp_path: Path, monkeypatch) -> None:
    outputs = _outputs(tmp_path / "main")
    first = HistoryFiles(outputs, 1).times
    assert len(first) == len(TIMES) and (outputs / TIMES_INDEX).is_file()

    def no_reading(*_: object) -> None:
        raise AssertionError("read again")

    monkeypatch.setattr(history, "_file_times", no_reading)
    assert list(HistoryFiles(outputs, 1).times) == list(first)

    # A file written again is read again
    path = outputs / "wrfout_d01_2025-10-01_00-00-00"
    later = path.stat().st_mtime + 60
    os.utime(path, (later, later))
    with pytest.raises(AssertionError, match="read again"):
        _ = HistoryFiles(outputs, 1).times


def test_the_import_writes_the_times_it_already_read(tmp_path: Path) -> None:
    source = _outputs(tmp_path / "source")
    target = tmp_path / "run" / "outputs" / "main"
    target.mkdir(parents=True)
    copies = []
    for path in source.iterdir():
        destination = target / path.name
        destination.write_bytes(path.read_bytes())
        copies.append((path, destination))
    record_times(target, copies)
    index = json.loads((target / TIMES_INDEX).read_text(encoding="utf-8"))
    entry = index[str(target / "wrfout_d01_2025-10-01_00-00-00")]
    assert entry["times"][0].startswith("2025-10-01T00:00:00")
    assert len(HistoryFiles(target, 1).times) == len(TIMES)
