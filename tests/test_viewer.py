# Copyright (c) 2026 Taras Bulubas. All rights reserved.
# Use requires prior written permission; see LICENSE.

import json
import re
from pathlib import Path

import pytest

from train_wagons import YardInstance, baseline_plan
from train_wagons.cli import main
from train_wagons.viewer import viewer_data, viewer_html, write_viewer

THREE_TRAINS = ((("A", 10.0), ("B", 10.0)), (("B", 10.0), ("A", 10.0)), (("A", 10.0),))


def test_viewer_embeds_instance_and_plan() -> None:
    instance = YardInstance(THREE_TRAINS, lanes=2, capacity=30.0)
    plan = baseline_plan(instance)
    html = viewer_html(instance, plan)
    data = json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', html, re.S).group(1))
    assert data == json.loads(json.dumps(viewer_data(instance, plan)))
    assert data["lanes"] == 2 and data["capacity"] == 30.0
    assert [[w["goods"] for w in t] for t in data["trains"]] == [["A", "B"], ["B", "A"], ["A"]]
    assert data["loads"] == [[k, p, lane] for (k, p), lane in plan.loads]
    assert data["errors"] == []
    assert set(data["colors"]) == {"A", "B"}
    assert "$" not in html.split('<script id="data"')[0]  # every template field was filled


def test_write_viewer_and_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    instance = YardInstance(THREE_TRAINS, lanes=2, capacity=30.0)
    path = write_viewer(instance, baseline_plan(instance), tmp_path / "sub" / "plan.html")
    assert path.exists() and "Plan Viewer" in path.read_text(encoding="utf-8")
    out = tmp_path / "cli.html"
    main(["--trains", "2", "--seed", "1", "--solver", "baseline", "--html", str(out)])
    assert out.exists()
    assert "viewer:" in capsys.readouterr().out
