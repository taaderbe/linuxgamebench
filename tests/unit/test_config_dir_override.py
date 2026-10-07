"""LGB_CONFIG_DIR keeps a stage test build's login apart from the normal install."""

import subprocess
import sys


def paths(env_extra):
    code = ("from linux_game_benchmark.config.settings import settings; "
            "print(settings.CONFIG_DIR); print(settings.AUTH_FILE); print(settings.CONFIG_FILE)")
    import os
    env = {k: v for k, v in os.environ.items() if k not in ("LGB_CONFIG_DIR", "XDG_CONFIG_HOME")}
    env.update(env_extra)
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True)
    return out.stdout.split("\n")[:3]


def test_override_moves_auth_and_config_file(tmp_path):
    target = tmp_path / "lgb-preprod"
    config_dir, auth_file, config_file = paths({"LGB_CONFIG_DIR": str(target), "XDG_CONFIG_HOME": str(tmp_path / "xdg")})
    assert config_dir == str(target)
    assert auth_file == str(target / "auth.json")
    assert config_file == str(target / "config.json")


def test_default_is_unchanged_xdg_location(tmp_path):
    config_dir, auth_file, _ = paths({"XDG_CONFIG_HOME": str(tmp_path / "xdg")})
    assert config_dir == str(tmp_path / "xdg" / "lgb")
    assert auth_file == str(tmp_path / "xdg" / "lgb" / "auth.json")


def test_empty_override_is_ignored(tmp_path):
    config_dir, _, _ = paths({"LGB_CONFIG_DIR": "", "XDG_CONFIG_HOME": str(tmp_path / "xdg")})
    assert config_dir == str(tmp_path / "xdg" / "lgb")
