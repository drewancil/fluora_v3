"""Dataclasses for fluora datatypes"""

from dataclasses import dataclass
from typing import Any

from .enums import FluoraScene


@dataclass(frozen=True)
class FluoraDiscovery:
    """Represent one plant discovered through the Fluora discovery broadcast."""

    address: str
    serial: str
    nickname: str
    model: str
    firmware_version: str
    revisions: dict[str, Any]
    raw: dict[str, Any]


@dataclass(frozen=True)
class ParameterIds:
    """Store captured parameter IDs for common Fluora controls."""

    hue: str = "HMKtSa"
    brightness: str = "vChKsv"
    saturation: str = "opm8As"
    effect: str = "SABJSE"
    is_displaying: str = "phnzVG"
    mode: str = "Cxu5QC"
    active_scene: str = "NxqQRg"


SCENE_ANIMATION_PARAMETER_IDS: dict[FluoraScene, str] = {
    FluoraScene.PARTY: "k6a7hH",
    FluoraScene.CHILL: "6YmROH",
    FluoraScene.FOCUS: "EZ8qj3",
    FluoraScene.BEDTIME: "r91cJJ",
    FluoraScene.AWAKEN: "dPwxUU",
}
