"""A small PNG reader and writer, standard library only, so map images can
be drawn on without image packages.

Reads 8-bit grayscale, RGB, RGBA and gray-alpha images, and palette images of
1, 2, 4 or 8 bits (with transparency), not interlaced: what map images from
wikis and emulators use. Writes 8-bit RGBA.

    image = Image.read("route202.png")
    image.fill_rect(8, 0, 24, 16, (255, 0, 0, 128))   # half-transparent red tile
    image.write("out.png")
"""

import struct
import zlib
from typing import List, Tuple

SIGNATURE = b"\x89PNG\r\n\x1a\n"

#   Color types (PNG spec 11.2.2) and their samples per pixel.
GRAY, RGB, PALETTE, GRAY_ALPHA, RGBA = 0, 2, 3, 4, 6
CHANNELS = {GRAY: 1, RGB: 3, PALETTE: 1, GRAY_ALPHA: 2, RGBA: 4}

#   Row filter types (PNG spec 9.2).
FILTER_NONE, FILTER_SUB, FILTER_UP, FILTER_AVERAGE, FILTER_PAETH = range(5)

OPAQUE = 255

Color = Tuple[int, int, int, int]


class Image:
    """An RGBA image: `width` x `height` pixels, 4 bytes each, row by row."""

    def __init__(self, width: int, height: int, fill: Color = (0, 0, 0, 0)):
        self.width = width
        self.height = height
        self.pixels = bytearray(bytes(fill) * (width * height))

    def get(self, x: int, y: int) -> Color:
        i = 4 * (y * self.width + x)
        return tuple(self.pixels[i:i + 4])

    def set(self, x: int, y: int, color: Color) -> None:
        i = 4 * (y * self.width + x)
        self.pixels[i:i + 4] = bytes(color)

    def fill_rect(self, x0: int, y0: int, x1: int, y1: int, color: Color) -> None:
        """Blends `color` over the pixels in [x0, x1) x [y0, y1), clipped to
        the image, by its alpha."""
        for y in range(max(0, y0), min(self.height, y1)):
            for x in range(max(0, x0), min(self.width, x1)):
                self.set(x, y, _blend(self.get(x, y), color))

    @classmethod
    def read(cls, path: str) -> "Image":
        with open(path, "rb") as f:
            return decode(f.read())

    def write(self, path: str) -> None:
        with open(path, "wb") as f:
            f.write(encode(self))


def _blend(under: Color, over: Color) -> Color:
    """`over` drawn on `under` with `over`'s alpha; the result is opaque if
    `under` was."""
    alpha = over[3] / OPAQUE
    rgb = [round(o * alpha + u * (1 - alpha)) for o, u in zip(over[:3], under[:3])]
    return (rgb[0], rgb[1], rgb[2], max(under[3], over[3]))


#   ---- writing ----

def encode(image: Image) -> bytes:
    """The PNG file bytes of `image`, as 8-bit RGBA."""
    header = struct.pack(">IIBBBBB", image.width, image.height, 8, RGBA, 0, 0, 0)
    stride = 4 * image.width
    raw = b"".join(bytes([FILTER_NONE]) + bytes(image.pixels[y * stride:(y + 1) * stride])
                   for y in range(image.height))
    return SIGNATURE + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(raw)) + _chunk(b"IEND", b"")


def _chunk(kind: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(kind + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)


#   ---- reading ----

def decode(data: bytes) -> Image:
    """An Image from PNG file bytes. Raises ValueError for what this reader
    does not handle (16-bit samples, interlacing)."""
    if not data.startswith(SIGNATURE):
        raise ValueError("not a PNG file")
    chunks = _chunks(data)
    width, height, depth, color_type, _, _, interlace = struct.unpack(">IIBBBBB", chunks[b"IHDR"][0])
    if interlace or depth > 8 or color_type not in CHANNELS:
        raise ValueError("unsupported PNG: depth %d, color type %d, interlace %d" % (depth, color_type, interlace))
    rows = _unfilter(zlib.decompress(b"".join(chunks.get(b"IDAT", []))), width, height,
                     CHANNELS[color_type], depth)
    palette = _palette(chunks)
    image = Image(width, height)
    for y, row in enumerate(rows):
        samples = _samples(row, width * CHANNELS[color_type], depth)
        for x in range(width):
            image.set(x, y, _to_rgba(samples, x, color_type, depth, palette))
    return image


def _chunks(data: bytes):
    chunks = {}
    pos = len(SIGNATURE)
    while pos < len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        chunks.setdefault(kind, []).append(data[pos + 8:pos + 8 + length])
        pos += 12 + length
    return chunks


def _palette(chunks) -> List[Color]:
    if b"PLTE" not in chunks:
        return []
    raw = chunks[b"PLTE"][0]
    alpha = chunks.get(b"tRNS", [b""])[0]
    return [(raw[i], raw[i + 1], raw[i + 2], alpha[i // 3] if i // 3 < len(alpha) else OPAQUE)
            for i in range(0, len(raw), 3)]


def _unfilter(raw: bytes, width: int, height: int, channels: int, depth: int) -> List[bytearray]:
    """The image's rows with the PNG row filters undone."""
    stride = (width * channels * depth + 7) // 8
    step = max(1, channels * depth // 8)
    rows = []
    previous = bytearray(stride)
    pos = 0
    for _ in range(height):
        kind = raw[pos]
        row = bytearray(raw[pos + 1:pos + 1 + stride])
        pos += 1 + stride
        _unfilter_row(kind, row, previous, step)
        rows.append(row)
        previous = row
    return rows


def _unfilter_row(kind: int, row: bytearray, previous: bytearray, step: int) -> None:
    for i in range(len(row)):
        left = row[i - step] if i >= step else 0
        up = previous[i]
        up_left = previous[i - step] if i >= step else 0
        if kind == FILTER_SUB:
            row[i] = (row[i] + left) & 0xFF
        elif kind == FILTER_UP:
            row[i] = (row[i] + up) & 0xFF
        elif kind == FILTER_AVERAGE:
            row[i] = (row[i] + (left + up) // 2) & 0xFF
        elif kind == FILTER_PAETH:
            row[i] = (row[i] + _paeth(left, up, up_left)) & 0xFF


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def _samples(row: bytearray, count: int, depth: int) -> List[int]:
    """The row's `count` samples, unpacked from `depth` bits each."""
    if depth == 8:
        return list(row[:count])
    per_byte = 8 // depth
    mask = (1 << depth) - 1
    samples = []
    for byte in row:
        for k in range(per_byte):
            samples.append((byte >> (8 - depth * (k + 1))) & mask)
    return samples[:count]


def _to_rgba(samples: List[int], x: int, color_type: int, depth: int, palette: List[Color]) -> Color:
    if color_type == PALETTE:
        return palette[samples[x]]
    n = CHANNELS[color_type]
    pixel = samples[x * n:(x + 1) * n]
    scale = OPAQUE // ((1 << depth) - 1)
    if color_type == GRAY:
        g = pixel[0] * scale
        return (g, g, g, OPAQUE)
    if color_type == GRAY_ALPHA:
        return (pixel[0], pixel[0], pixel[0], pixel[1])
    if color_type == RGB:
        return (pixel[0], pixel[1], pixel[2], OPAQUE)
    return tuple(pixel)
