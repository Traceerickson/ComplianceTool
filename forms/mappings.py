from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Optional

import yaml


@dataclass
class CmmMapping:
    characteristic_id: str = "Characteristic ID"
    description: Optional[str] = None
    measured: str = "Measured"
    unit: str = "Unit"
    instrument: Optional[str] = None


def load_cmm_mapping(config_path: str = "config/cmm_mappings.yaml") -> CmmMapping:
    if not os.path.exists(config_path):
        return CmmMapping()
    with open(config_path, "r", encoding="utf-8") as f:
        data: Dict = yaml.safe_load(f) or {}
    cfg = data.get("cmm_columns", {})
    return CmmMapping(
        characteristic_id=cfg.get("characteristic_id", "Characteristic ID"),
        description=cfg.get("description"),
        measured=cfg.get("measured", "Measured"),
        unit=cfg.get("unit", "Unit"),
        instrument=cfg.get("instrument"),
    )

