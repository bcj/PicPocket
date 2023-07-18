"""Colour scheme definitions"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ColorScheme:
    background: str
    text: str
    accent: str
    accent_text: str
    link_accent: str
    border: str
    secondary: str


LIGHT = ColorScheme(
    background="#E7E9EE",
    text="black",
    accent="#820933",
    accent_text="#D0D8DC",
    link_accent="#331774",
    border="#96A7B0",
    secondary="#8B9DA7",
)


DARK = ColorScheme(
    background="#424C55",
    text="#E7E9EE",
    accent="#E9B872",
    accent_text="black",
    link_accent="#B0A3D4",
    border="#E7E9EE",
    secondary="#232A2E",
)


__all__ = ("DARK", "LIGHT", "ColorScheme")
