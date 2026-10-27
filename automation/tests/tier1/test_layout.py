"""Tier 1: real WPF layout rules and Today ring sizing."""

from __future__ import annotations

import math
from core.model_probe import probe


def children(heights, collapsed=()):
    collapsed = set(collapsed)
    return [{"height": height, "collapsed": i in collapsed} for i, height in enumerate(heights)]


def layout(heights, width=1000, *, min_width=200, max_columns=4, spacing=16, fill=False, collapsed=()):
    return probe({"cmd": "adaptive-columns", "width": width, "min": min_width,
                  "max": max_columns, "spacing": spacing, "fill": fill,
                  "children": children(heights, collapsed)})


class TestAdaptiveColumns:
    def test_row_members_share_the_tallest_height_and_reading_order(self):
        row = layout([100, 200, 150], width=700, max_columns=3, spacing=10)
        assert [s["y"] for s in row["children"]] == [0, 0, 0]
        assert [s["height"] for s in row["children"]] == [200, 200, 200]
        reading_order = layout([10] * 5, width=700, max_columns=3, spacing=10)["children"]
        assert [(s["y"], s["x"]) for s in reading_order] == [(0, 0), (0, (700 - 2 * 10) / 3 + 10), (0, 2 * ((700 - 2 * 10) / 3 + 10)), (20, 0), (20, (700 - 2 * 10) / 3 + 10)]
        assert row["desiredHeight"] == 200

    def test_balances_rows_by_reducing_the_column_count(self):
        five = layout([10] * 5, width=1000, min_width=200, max_columns=4)
        four = layout([10] * 4, width=800, min_width=200, max_columns=3)
        assert [s["x"] for s in five["children"]] == [0, (1000 - 2 * 16) / 3 + 16, 2 * ((1000 - 2 * 16) / 3 + 16), 0, (1000 - 2 * 16) / 3 + 16]
        assert [s["x"] for s in four["children"]] == [0, 408, 0, 408]

    def test_fill_last_row_spans_width_only_when_enabled(self):
        # BalancedColumns does not leave a one-card row for these counts; the
        # shortest possible final row here has two cards. Both share that row.
        filled = layout([10] * 5, width=700, min_width=200, max_columns=3, fill=True)
        fixed = layout([10] * 5, width=700, min_width=200, max_columns=3, fill=False)
        assert [s["width"] for s in filled["children"][3:]] == [342, 342]
        assert [s["width"] for s in fixed["children"][3:]] == [(700 - 2 * 16) / 3] * 2
        lone = layout([10], width=700, min_width=200, max_columns=3, fill=True)
        one_column = layout([10], width=700, min_width=200, max_columns=3, fill=False)
        assert lone["children"][0]["width"] == 700
        assert one_column["children"][0]["width"] == 700

    def test_collapsed_children_take_no_slot(self):
        result = layout([10, 20, 30, 40], width=700, max_columns=3, collapsed=[1])
        slots = result["children"]
        assert slots[1]["visible"] is False
        assert slots[1]["width"] == slots[1]["height"] == 0
        assert slots[0]["y"] == slots[2]["y"] == slots[3]["y"] == 0

    def test_narrow_width_uses_one_column_and_rows_contribute_to_desired_height(self):
        result = layout([100, 200, 150], width=409, min_width=200, max_columns=4, spacing=10)
        assert [slot["x"] for slot in result["children"]] == [0, 0, 0]
        assert result["desiredHeight"] == 470


class TestRingSizeFor:
    def test_clamps_scales_monotonically_and_handles_non_finite_heights(self):
        heights = [0, 400, 700, 900, 1200, 2000, "NaN", "Infinity", "-Infinity"]
        sizes = probe({"cmd": "ring-size", "heights": heights})["sizes"]
        assert sizes[:1] == [222]
        assert sizes[1:6] == sorted(sizes[1:6])
        assert sizes[1] == 222 and sizes[5] == 320
        assert sizes[6:] == [222, 222, 222]
