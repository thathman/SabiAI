"""Canonical Sabi dashboard artwork.

The V1 dashboard generated its install icon from a small pixel grid.  Keeping
that implementation here gives V2 one source for the favicon, sidebar mark,
and all PWA icon sizes instead of allowing a font-rendered substitute to
drift between surfaces.
"""

from __future__ import annotations

import struct
import zlib


V1_ICON_BACKGROUND = (12, 10, 7)  # #0c0a07
V1_ICON_GOLD = (230, 178, 82)  # #e6b252
V1_ICON_GRID = (
    "011110",
    "100001",
    "100000",
    "011110",
    "000001",
    "100001",
    "011110",
)


def make_v1_icon_png(size: int) -> bytes:
    """Return the exact V1 pixel-block S as a valid RGB PNG."""

    if size <= 0:
        raise ValueError("icon size must be positive")

    bg_r, bg_g, bg_b = V1_ICON_BACKGROUND
    ac_r, ac_g, ac_b = V1_ICON_GOLD
    cell = max(1, size // 8)
    rows: list[bytes] = []
    for y in range(size):
        row: list[int] = []
        gy = (y - (size - 7 * cell) // 2) // cell
        for x in range(size):
            gx = (x - (size - 6 * cell) // 2) // cell
            if 0 <= gy < 7 and 0 <= gx < 6 and V1_ICON_GRID[gy][gx] == "1":
                row.extend((ac_r, ac_g, ac_b))
            else:
                row.extend((bg_r, bg_g, bg_b))
        rows.append(b"\x00" + bytes(row))

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", crc)
        )

    raw = b"".join(rows)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def v1_icon_svg() -> str:
    """Return a vector version of the same V1 grid for legacy SVG URLs."""

    cell = 24
    x0, y0 = 24, 12
    rects: list[str] = []
    for row, bits in enumerate(V1_ICON_GRID):
        for col, bit in enumerate(bits):
            if bit == "1":
                rects.append(
                    f"<rect x='{x0 + col * cell}' y='{y0 + row * cell}' "
                    f"width='{cell}' height='{cell}' fill='#e6b252'/>"
                )
    return (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 192 192' "
        "shape-rendering='crispEdges'>"
        "<rect width='192' height='192' fill='#0c0a07'/>"
        + "".join(rects)
        + "</svg>"
    )
