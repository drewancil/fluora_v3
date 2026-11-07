"""Enumerations for Fluora plant controls."""

from enum import IntEnum


class FluoraMode(IntEnum):
    """Define Fluora operating mode values captured from firmware 3.x."""

    AUTO = 0
    SCENE = 1
    MANUAL = 2


class FluoraScene(IntEnum):
    """Define Fluora scene values captured from firmware 3.x."""

    PARTY = 0
    CHILL = 1
    FOCUS = 2
    BEDTIME = 3
    AWAKEN = 4


class FluoraEffect(IntEnum):
    """Define Fluora animation effect indices captured from firmware 3.x."""

    TWINKLE = 0
    LEAF_SWIRL = 1
    MIRAGE = 2
    RAINBOW = 3
    RAINBOW_BLOOM = 4
    RAINBOW_SWIRL = 5
    BREEZE = 6
    SNAKES = 7
    WAVES = 8
    BEAM = 9
    LIGHTHOUSE = 10
    HUE_CYCLE = 11
    HUES = 12
    GRADIENT = 13
    LEAF_FADE = 14
    STEM_FADE = 15
    SWEEP = 16
    PULSE = 17
    LAMP = 18
    SOLID_COLOR = 19
    BOOM_CLAP = 20
    STEM_EQ = 21
    EQUALIZER = 22
    EQ_DOTS = 23
    PITCH = 24
    HUE_EQ = 25
    LEAF_EQ = 26
    SHOCKWAVE = 27
    STAR_SPANGLED_BANNER = 28
    STAR_SPANGLED_SPARKLE = 29
    HALLOWEEN_FADE = 30
    HALLOWEEN_TWINKLE = 31
    HOLIDAY_FADE = 32
    HOLIDAY_RIPPLE = 33
    HOLIDAY_TWINKLE = 34

    @property
    def label(self) -> str:
        """Return the display label exposed by the plant."""
        return EFFECT_LABELS[self]

    @classmethod
    def from_value(cls, value: FluoraEffect | int | str) -> FluoraEffect:
        """Resolve an effect enum, index, member name, or display label."""
        if isinstance(value, cls):
            return value
        if isinstance(value, bool):
            raise ValueError(f"unknown Fluora effect: {value}")
        if isinstance(value, int):
            return cls(value)

        stripped = value.strip()
        if not stripped:
            raise ValueError("Fluora effect must not be empty")
        try:
            return cls(int(stripped))
        except ValueError:
            pass

        normalized = _normalize_effect_name(stripped)
        for effect in cls:
            if normalized in {
                _normalize_effect_name(effect.name),
                _normalize_effect_name(effect.label),
            }:
                return effect
        raise ValueError(f"unknown Fluora effect: {value}")


EFFECT_LABELS: dict[FluoraEffect, str] = {
    FluoraEffect.TWINKLE: "Twinkle",
    FluoraEffect.LEAF_SWIRL: "Leaf Swirl",
    FluoraEffect.MIRAGE: "Mirage",
    FluoraEffect.RAINBOW: "Rainbow",
    FluoraEffect.RAINBOW_BLOOM: "Rainbow Bloom",
    FluoraEffect.RAINBOW_SWIRL: "Rainbow Swirl",
    FluoraEffect.BREEZE: "Breeze",
    FluoraEffect.SNAKES: "Snakes",
    FluoraEffect.WAVES: "Waves",
    FluoraEffect.BEAM: "Beam",
    FluoraEffect.LIGHTHOUSE: "Lighthouse",
    FluoraEffect.HUE_CYCLE: "Hue Cycle",
    FluoraEffect.HUES: "Hues",
    FluoraEffect.GRADIENT: "Gradient",
    FluoraEffect.LEAF_FADE: "Leaf Fade",
    FluoraEffect.STEM_FADE: "Stem Fade",
    FluoraEffect.SWEEP: "Sweep",
    FluoraEffect.PULSE: "Pulse",
    FluoraEffect.LAMP: "Lamp",
    FluoraEffect.SOLID_COLOR: "Solid Color",
    FluoraEffect.BOOM_CLAP: "Boom Clap",
    FluoraEffect.STEM_EQ: "StemEQ",
    FluoraEffect.EQUALIZER: "Equalizer",
    FluoraEffect.EQ_DOTS: "EQ Dots",
    FluoraEffect.PITCH: "Pitch",
    FluoraEffect.HUE_EQ: "HueEQ",
    FluoraEffect.LEAF_EQ: "LeafEQ",
    FluoraEffect.SHOCKWAVE: "Shockwave",
    FluoraEffect.STAR_SPANGLED_BANNER: "Star Spangled Banner",
    FluoraEffect.STAR_SPANGLED_SPARKLE: "Star Spangled Sparkle",
    FluoraEffect.HALLOWEEN_FADE: "Halloween Fade",
    FluoraEffect.HALLOWEEN_TWINKLE: "Halloween Twinkle",
    FluoraEffect.HOLIDAY_FADE: "Holiday Fade",
    FluoraEffect.HOLIDAY_RIPPLE: "Holiday Ripple",
    FluoraEffect.HOLIDAY_TWINKLE: "Holiday Twinkle",
}

SCENE_EFFECTS: tuple[FluoraEffect, ...] = tuple(
    effect
    for effect in FluoraEffect
    if effect
    not in {
        FluoraEffect.WAVES,
        FluoraEffect.BEAM,
        FluoraEffect.LIGHTHOUSE,
        FluoraEffect.HUES,
        FluoraEffect.EQUALIZER,
        FluoraEffect.EQ_DOTS,
        FluoraEffect.PITCH,
    }
)


def _normalize_effect_name(value: str) -> str:
    """Normalize an effect name for case-insensitive matching."""
    return "".join(character.lower() for character in value if character.isalnum())
