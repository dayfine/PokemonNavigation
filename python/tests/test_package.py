"""Checks that the package imports, so CI fails early on a broken layout."""

import unittest

import pokenav


class PackageTest(unittest.TestCase):
    def test_imports_with_a_version(self):
        self.assertRegex(pokenav.__version__, r"^\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
