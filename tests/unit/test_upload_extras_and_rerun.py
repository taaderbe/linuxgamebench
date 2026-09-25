"""Upload response extras (share link, standing, pioneer) and re-run hints."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from linux_game_benchmark.api.client import BenchmarkAPIClient
from linux_game_benchmark.benchmark import env_tracker
from linux_game_benchmark.config.settings import settings


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    return tmp_path


SYSTEM = {"gpu": "RX 7900 XTX", "gpu_driver": "25.1.0", "kernel": "6.17", "proton_build": "proton-9.0-4f"}


class TestEnvTracker:
    def test_record_and_no_change(self, config_dir):
        env_tracker.record_upload(238960, "Path of Exile", SYSTEM)
        assert (config_dir / "last_env.json").exists()
        assert env_tracker.driver_changes("RX 7900 XTX", "25.1.0") == []

    def test_driver_change_detected(self, config_dir):
        env_tracker.record_upload(238960, "Path of Exile", SYSTEM)
        changes = env_tracker.driver_changes("RX 7900 XTX", "25.2.0")
        assert changes == [{"app_id": 238960, "name": "Path of Exile", "old": "25.1.0", "new": "25.2.0"}]

    def test_other_gpu_ignored(self, config_dir):
        env_tracker.record_upload(238960, "Path of Exile", SYSTEM)
        assert env_tracker.driver_changes("RTX 4070", "580.1") == []

    def test_unknown_current_driver_no_hint(self, config_dir):
        env_tracker.record_upload(238960, "Path of Exile", SYSTEM)
        assert env_tracker.driver_changes("RX 7900 XTX", None) == []

    def test_proton_change_detected(self, config_dir, tmp_path):
        env_tracker.record_upload(238960, "Path of Exile", SYSTEM)
        prefix = tmp_path / "compatdata" / "238960"
        prefix.mkdir(parents=True)
        with patch("linux_game_benchmark.steam.proton_detect._compatdata_dirs", return_value=[prefix]), \
             patch("linux_game_benchmark.steam.proton_detect.read_prefix_proton",
                   return_value={"proton_build": "proton-10.0-1"}):
            changes = env_tracker.proton_changes()
        assert changes[0]["old"] == "proton-9.0-4f" and changes[0]["new"] == "proton-10.0-1"

    def test_hints_text(self, config_dir):
        env_tracker.record_upload(238960, "Path of Exile", SYSTEM)
        env_tracker.record_upload(526870, "Satisfactory", SYSTEM)
        with patch.object(env_tracker, "proton_changes", return_value=[]):
            hints = env_tracker.rerun_hints("RX 7900 XTX", "25.2.0")
        assert len(hints) == 1
        assert "25.1.0 → 25.2.0" in hints[0]
        assert "Path of Exile" in hints[0] and "Satisfactory" in hints[0]

    def test_corrupt_file_is_ignored(self, config_dir):
        (config_dir / "last_env.json").write_text("{not json")
        assert env_tracker.rerun_hints("RX 7900 XTX", "25.2.0") == []
        env_tracker.record_upload(238960, "Path of Exile", SYSTEM)  # overwrites cleanly
        assert env_tracker.driver_changes("RX 7900 XTX", "25.2.0")

    def test_no_app_id_not_recorded(self, config_dir):
        env_tracker.record_upload(0, "Unknown", SYSTEM)
        assert not (config_dir / "last_env.json").exists()


class TestUploadResultExtras:
    def _upload(self, response_json):
        resp = MagicMock(status_code=200)
        resp.json.return_value = response_json
        http = MagicMock()
        http.__enter__.return_value.post.return_value = resp
        with patch("linux_game_benchmark.api.client.httpx.Client", return_value=http):
            return BenchmarkAPIClient(base_url="http://test/api/v1").upload_benchmark(
                steam_app_id=238960, game_name="Path of Exile", resolution="2560x1440",
                system_info={"gpu": "RX 7900 XTX", "gpu_driver": "25.1.0"},
                metrics={"fps_avg": 100}, require_auth=False,
            )

    def test_new_server_fields(self, config_dir):
        result = self._upload({
            "id": 289, "share_url": "https://linuxgamebench.com/run/289",
            "standing": {"text": "Fastest of 3 setups in Path of Exile at 1440p.", "rank": 1},
            "pioneer": True,
            "new_achievements": [{"id": "pioneer", "name": "Pioneer", "icon": "🧭"}],
        })
        assert result.success and result.benchmark_id == 289
        assert result.url == "https://linuxgamebench.com/run/289"
        assert result.standing["rank"] == 1
        assert result.pioneer is True
        assert result.achievements[0]["id"] == "pioneer"
        # successful upload is remembered for re-run hints
        assert env_tracker.driver_changes("RX 7900 XTX", "25.2.0")

    def test_old_server_response(self, config_dir):
        result = self._upload({"id": 5, "message": "Benchmark submitted successfully"})
        assert result.success and result.url is None
        assert result.standing is None and result.pioneer is False and result.achievements == []
