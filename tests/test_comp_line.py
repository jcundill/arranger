"""Tests for the comp line rules."""

from __future__ import annotations

import unittest

from arranger import comp_line


class TestHomeBand(unittest.TestCase):
    def test_shipped_window(self) -> None:
        self.assertEqual(comp_line.home_band(2, 13), (3, 10))

    def test_clamped(self) -> None:
        self.assertEqual(comp_line.home_band(10, 13), (11, 13))


class TestWalk(unittest.TestCase):
    def test_walks_up(self) -> None:
        tone, direction = comp_line.walk_step(60, 1, [58, 62, 64], [])
        self.assertEqual(tone, 62)
        self.assertEqual(direction, 1)

    def test_no_retrace(self) -> None:
        tone, _ = comp_line.walk_step(62, 1, [60, 62, 64], [60, 62])
        self.assertNotEqual(tone, 60)


class TestApproach(unittest.TestCase):
    def test_approach_nearest(self) -> None:
        self.assertEqual(comp_line.approach(60, 67, [62, 65, 67]), 67)


class TestOpening(unittest.TestCase):
    def test_no_melody(self) -> None:
        self.assertEqual(comp_line.opening_no_melody([60, 64, 67], (3, 10)), 60)


class TestInterpolate(unittest.TestCase):
    def test_endpoints(self) -> None:
        out = comp_line.interpolate(60, 72, 4)
        self.assertEqual(out[0], 60)
        self.assertEqual(out[-1], 72)


if __name__ == "__main__":
    unittest.main()
