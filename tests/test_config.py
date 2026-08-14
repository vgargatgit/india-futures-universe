from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from india_futures_universe.config import load_config


def test_config_rejects_unknown_top_level_key(tmp_path: Path) -> None:
    payload = yaml.safe_load(Path("configs/nse_futures_data.yaml").read_text())
    payload["unexpected"] = True
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(payload))
    with pytest.raises(ValueError, match="Unknown top-level"):
        load_config(path)


def test_config_loads_project_id() -> None:
    config = load_config("configs/nse_futures_data.yaml")
    assert config.project_id == "INDIA_FUTURES_UNIVERSE_V1"
    assert config.research.instrument_types == ("FUTSTK",)
