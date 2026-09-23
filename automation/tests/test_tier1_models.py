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
