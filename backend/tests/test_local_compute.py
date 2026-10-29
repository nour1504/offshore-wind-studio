"""The engine on this computer only: old settings keep loading, the installer stays."""

import json
from pathlib import Path
from unittest.mock import Mock

from helpers import make_client, wsl_profile

from owstudio.core import docs
from owstudio.core.engine import install
from owstudio.core.engine.profiles import ComputeProfile
from owstudio.core.engine.shells import Shell
from owstudio.core.settings import load_settings


def test_local_installation_uses_the_chosen_folder_outside_home() -> None:
    target = Mock(spec=Shell)
    target.run.side_effect = AssertionError("a chosen root needs no HOME probe")
    profile = ComputeProfile(id="native", name="Local Linux", kind="local")
    request = install.InstallRequest(profile=profile, root="/mnt/models/offshore-engine")
    assert install.resolve_root(target, request) == "/mnt/models/offshore-engine"
    target.run.assert_not_called()


def test_catalog_exposes_local_paths_without_starting_installation(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    result = client.get("/api/engine/catalog").json()
    assert result["host_platform"]
    assert result["native_root"] == str(Path.home() / "OffshoreWindStudioEngine" / result["id"])
    assert result["local_folder"] == str(tmp_path / "data/engine-wsl")
    assert client.get("/api/engine/installations").json() == []


def test_old_remote_profiles_are_left_out_without_rewriting_the_file(tmp_path: Path) -> None:
    old = {
        "data_root": str(tmp_path / "data"),
        "default_profile": "old-cluster",
        "profiles": [
            wsl_profile().model_dump(),
            {"id": "old-server", "name": "Old server", "kind": "ssh",
             "ssh": {"host": "vm", "user": "researcher", "port": 2222}},
            {"id": "old-cluster", "name": "Old cluster", "kind": "slurm",
             "ssh": {"host": "hpc", "user": "researcher"},
             "slurm": {"partition": "science", "modules": ["mpi/site"]}},
        ],
    }  # fmt: skip
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(old), encoding="utf-8")
    before = path.read_bytes()
    loaded = load_settings(path)
    assert [profile.model_dump() for profile in loaded.profiles] == [wsl_profile().model_dump()]
    assert loaded.default_profile == "wsl-test"
    assert path.read_bytes() == before


def test_help_of_what_was_removed_is_gone(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    removed = {"ssh", "slurm", "campaigns", "scenarios", "file-locations"}
    for lang in docs.LANGS:
        topics = docs.topics(lang)
        assert {"compute", "engine-install"} <= set(topics)
        assert not removed & set(topics)
        assert not {hit.id for hit in docs.search("Slurm", lang)} & removed
        for name in removed:
            assert client.get(f"/api/docs/{name}", params={"lang": lang}).status_code == 404
