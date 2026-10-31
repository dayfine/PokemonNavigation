"""Tests for pokenav.cli.textgrid: showing and converting maps."""

import contextlib
import io
import os
import tempfile
import unittest

from pokenav.cli import textgrid as cli
from pokenav.grid.maps import schema, textgrid

from tests.paths import DOCS_EXAMPLES
from tests.test_maps_textgrid import SMALL


class CommandLineTest(unittest.TestCase):
    def run_main(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(list(argv)), 0)
        return out.getvalue()

    def test_show_the_example(self):
        out = self.run_main("show", os.path.join(DOCS_EXAMPLES, "tiny_town.json"))
        self.assertIn("#N#  // 1", out)

    def test_convert_text_to_json_and_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            text_path = os.path.join(tmp, "small.txt")
            json_path = os.path.join(tmp, "small.json")
            back_path = os.path.join(tmp, "back.txt")
            with open(text_path, "w") as f:
                f.write(SMALL)
            self.run_main("convert", text_path, json_path)
            self.run_main("convert", json_path, back_path)
            self.assertEqual(schema.load(json_path), textgrid.parse(SMALL))
            with open(back_path) as f:
                self.assertEqual(textgrid.parse(f.read()), textgrid.parse(SMALL))


if __name__ == "__main__":
    unittest.main()
