# Copyright (c) 2026 Taras Bulubas. All rights reserved.
# Use requires prior written permission; see LICENSE.

import pytest

from train_wagons.cli import main


def test_cli_prints_a_checked_plan(capsys: pytest.CaptureFixture[str]) -> None:
    main(["--trains", "3", "--seed", "7"])
    out = capsys.readouterr().out
    assert "instance: 3 trains" in out
    assert "[T_3 leaves]" in out
    assert "check: OK" in out


def test_cli_rejects_unknown_criteria() -> None:
    with pytest.raises(ValueError):
        main(["--objective", "changes,speed"])
