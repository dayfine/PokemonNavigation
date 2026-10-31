"""Tests for pokenav.png: round trips, every row filter, palettes and low
bit depths, built from hand-made PNG bytes."""

import os
import struct
import tempfile
import unittest
import zlib

from pokenav import png
from pokenav.png import Image


def make_png(width, height, depth, color_type, rows, palette=b"", alpha=b""):
    """PNG bytes for `rows`, each a (filter type, row bytes) pair."""
    header = struct.pack(">IIBBBBB", width, height, depth, color_type, 0, 0, 0)
    raw = b"".join(bytes([kind]) + data for kind, data in rows)
    chunks = png._chunk(b"IHDR", header)
    if palette:
        chunks += png._chunk(b"PLTE", palette)
    if alpha:
        chunks += png._chunk(b"tRNS", alpha)
    return png.SIGNATURE + chunks + png._chunk(b"IDAT", zlib.compress(raw)) + png._chunk(b"IEND", b"")


class PngTest(unittest.TestCase):
    def test_round_trip(self):
        image = Image(3, 2, (10, 20, 30, 255))
        image.set(2, 1, (1, 2, 3, 4))
        back = png.decode(png.encode(image))
        self.assertEqual((back.width, back.height), (3, 2))
        self.assertEqual(back.pixels, image.pixels)

    def test_read_and_write_files(self):
        image = Image(2, 2, (5, 6, 7, 255))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.png")
            image.write(path)
            self.assertEqual(Image.read(path).pixels, image.pixels)

    def test_every_row_filter(self):
        #   A 2 x 1 gray image per filter, each decoding to samples 10 and 30.
        #   Row 0 sits over an implied row of zeros.
        cases = {
            png.FILTER_NONE: bytes([10, 30]),
            png.FILTER_SUB: bytes([10, 20]),
            png.FILTER_UP: bytes([10, 30]),
            png.FILTER_AVERAGE: bytes([10, 25]),
            png.FILTER_PAETH: bytes([10, 20]),
        }
        for kind, data in cases.items():
            image = png.decode(make_png(2, 1, 8, png.GRAY, [(kind, data)]))
            self.assertEqual([image.get(x, 0)[0] for x in range(2)], [10, 30], kind)

    def test_filters_use_the_row_above(self):
        rows = [(png.FILTER_NONE, bytes([100, 50])), (png.FILTER_UP, bytes([1, 2])),
                (png.FILTER_PAETH, bytes([0, 0]))]
        image = png.decode(make_png(2, 3, 8, png.GRAY, rows))
        self.assertEqual([image.get(x, 1)[0] for x in range(2)], [101, 52])
        #   Paeth over (101, 52) with nothing to the left picks the pixel above.
        self.assertEqual(image.get(0, 2)[0], 101)

    def test_rgb_and_gray_alpha(self):
        rgb = png.decode(make_png(1, 1, 8, png.RGB, [(0, bytes([1, 2, 3]))]))
        self.assertEqual(rgb.get(0, 0), (1, 2, 3, 255))
        ga = png.decode(make_png(1, 1, 8, png.GRAY_ALPHA, [(0, bytes([9, 99]))]))
        self.assertEqual(ga.get(0, 0), (9, 9, 9, 99))

    def test_palette_with_two_bits_and_transparency(self):
        palette = bytes([255, 0, 0, 0, 255, 0, 0, 0, 255])
        #   Four 2-bit indexes in one byte: 0, 1, 2, 1.
        image = png.decode(make_png(4, 1, 2, png.PALETTE, [(0, bytes([0b00011001]))], palette, bytes([128])))
        self.assertEqual([image.get(x, 0) for x in range(4)],
                         [(255, 0, 0, 128), (0, 255, 0, 255), (0, 0, 255, 255), (0, 255, 0, 255)])

    def test_unsupported(self):
        with self.assertRaises(ValueError):
            png.decode(b"GIF89a")
        with self.assertRaises(ValueError):
            png.decode(make_png(1, 1, 16, png.GRAY, [(0, bytes([0, 0]))]))

    def test_fill_rect_blends_and_clips(self):
        image = Image(4, 4, (0, 0, 0, 255))
        image.fill_rect(-2, -2, 2, 2, (255, 255, 255, 255))
        image.fill_rect(2, 2, 9, 9, (200, 100, 0, 128))
        self.assertEqual(image.get(1, 1), (255, 255, 255, 255))
        self.assertEqual(image.get(2, 1), (0, 0, 0, 255))
        self.assertEqual(image.get(3, 3), (100, 50, 0, 255))


if __name__ == "__main__":
    unittest.main()
