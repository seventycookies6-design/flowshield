"""
Tier 1 -- the real C# model code (1.0.10).

Every test here runs DesktopApp/Models through `core.model_probe`, so the
answer comes from .NET rather than from a Python copy of the rule. Kept apart
from test_tier1_unit.py so the two files can change independently.
"""

from __future__ import annotations

import pytest

from core.model_probe import ProbeError, probe


# ============================ the model probe: real C# from tier 1 (1.0.10)

class TestModelProbe:
    """
    Tier 1 mirrors C# rules in Python and pins the C# by source, because there
    is no dotnet test project. That can't prove the C# computes the answer,
    and for time zones .NET decides it, not Python. ModelProbe compiles
    DesktopApp/Models as it is and answers JSON, so these run the real code.
    """

    def test_the_probe_answers(self):
        assert probe({"cmd": "ping"}) == {"ok": True}

    def test_the_probe_runs_the_real_soft_overlay_policy(self):
        out = probe({"cmd": "soft-sequence", "steps": [
            {"op": "show", "app": "Discord", "at": 0},
            {"op": "show", "app": "Discord", "at": 2},
            {"op": "left"},
            {"op": "show", "app": "Discord", "at": 60},
        ]})
        assert out["results"] == [True, False, True, True]

    def test_an_unknown_command_is_an_error_not_a_silent_pass(self):
        with pytest.raises(ProbeError):
            probe({"cmd": "no-such-command"})


# ============================================ F6: study templates (1.0.10)

class TestStudyTemplates:
    """F6: the three built-ins from the launch checklist, and a template can't hold nonsense."""

    def _builtins(self) -> dict:
        return {t["BuiltInKey"]: t for t in probe({"cmd": "template-builtins"})["templates"]}

    def test_three_built_ins_ship_with_the_checklist_values(self):
        b = self._builtins()
        assert set(b) == {"homework", "exam", "light"}
        hw, ex, li = b["homework"], b["exam"], b["light"]
        assert (hw["Name"], hw["SprintMinutes"], hw["Shield"], hw["CycleSprints"], hw["BreakMinutes"]) \
            == ("Homework evening", 45, 2, 3, 10)
        assert (ex["Name"], ex["SprintMinutes"], ex["Shield"], ex["CycleSprints"]) \
            == ("Exam prep", 90, 3, 0)
        assert (li["Name"], li["SprintMinutes"], li["Shield"], li["CycleSprints"], li["BreakMinutes"]) \
            == ("Light study", 25, 1, 0, 5)

    def test_built_ins_use_whichever_profile_is_active(self):
        assert all(t["ProfileId"] == "" for t in self._builtins().values())

    def test_each_call_hands_out_fresh_ids(self):
        first = {t["Id"] for t in self._builtins().values()}
        second = {t["Id"] for t in self._builtins().values()}
        assert len(first) == 3 and not first & second

    @pytest.mark.parametrize("field,given,expected", [
        ("SprintMinutes", 2, 5),
        ("SprintMinutes", 500, 240),
        ("CycleSprints", 1, 0),
        ("CycleSprints", 7, 0),
        ("CycleSprints", 3, 3),
        ("BreakMinutes", 0, 1),
        ("BreakMinutes", 99, 60),
        ("Shield", 9, 2),
        ("Name", "   ", "Untitled template"),
        ("Name", "x" * 60, "x" * 40),
        ("Name", "  Mock exam  ", "Mock exam"),
        ("ProfileId", None, ""),
        ("BuiltInKey", None, ""),
    ])
    def test_normalize_clamps_every_field(self, field, given, expected):
        template = {"Id": "t1", "Name": "Mine", "SprintMinutes": 30, "Shield": 2,
                    "CycleSprints": 0, "BreakMinutes": 5, "ProfileId": "", "BuiltInKey": ""}
        template[field] = given
        out = probe({"cmd": "template-normalize", "template": template})
        assert out["template"][field] == expected
        assert out["changed"] is (given != expected)

    def test_normalize_gives_a_missing_id_a_new_one(self):
        out = probe({"cmd": "template-normalize", "template": {"Id": "", "Name": "A"}})
        assert len(out["template"]["Id"]) == 32 and out["changed"] is True
