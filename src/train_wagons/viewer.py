# Copyright (c) 2026 Taras Bulubas. All rights reserved.
# Use requires prior written permission; see LICENSE.

"""Interactive HTML viewer of a loading plan: port, buffer and departure track, step by step.

The page is self-contained (no external scripts) and replays the plan in the
browser: every wagon that is loaded and moved into its lane, and every train
that is assembled from the fronts of the lanes and leaves.
"""

from __future__ import annotations

import json
from pathlib import Path
from string import Template

from train_wagons.instance import YardInstance
from train_wagons.solution import LoadingPlan, simulate, train_spreads

PALETTE = ("#8ecae6", "#ffb703", "#90be6d", "#f4978e", "#cdb4db", "#bde0fe", "#e9c46a", "#a8dadc")


def viewer_data(instance: YardInstance, plan: LoadingPlan) -> dict:
    sim = simulate(instance, plan)
    m = sim.metrics
    summary = (
        f"{len(instance.trains)} trains, {instance.wagon_count} wagons, {len(instance.goods_types)} goods types,"
        f" {instance.lanes} lanes of {instance.capacity:g} t, load factor {instance.load_factor:.2f}"
    )
    result = f"plan: {plan.method or 'given'}, status {plan.status.value}"
    if m is not None:
        result += (
            f" — changes {m.changes}, lanes {m.lanes}, waiting {m.waiting}, peak {m.peak},"
            f" priority {m.priority:g}, largest spread {max(train_spreads(instance, plan.loads))}"
        )
    return {
        "summary": summary,
        "result": result,
        "errors": sim.errors,
        "lanes": instance.lanes,
        "capacity": instance.capacity,
        "colors": {g: PALETTE[n % len(PALETTE)] for n, g in enumerate(instance.goods_types)},
        "trains": [[{"goods": g, "weight": w} for g, w in train] for train in instance.trains],
        "loads": [[key[0], key[1], lane] for key, lane in plan.loads],
    }


def viewer_html(instance: YardInstance, plan: LoadingPlan, title: str = "Train Wagons Planning — Plan Viewer") -> str:
    data = json.dumps(viewer_data(instance, plan)).replace("</", "<\\/")
    return _PAGE.substitute(title=title, data=data)


def write_viewer(instance: YardInstance, plan: LoadingPlan, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(viewer_html(instance, plan), encoding="utf-8")
    return path


_PAGE = Template(r"""<!doctype html>
<!-- Copyright (c) 2026 Taras Bulubas. All rights reserved. Use requires prior written permission. -->
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$title</title>
<style>
  :root { --fg: #222; --muted: #666; --line: #ccc; --panel: #f6f6f6; --hi: #d62828; }
  body { font: 14px/1.4 system-ui, sans-serif; color: var(--fg); background: #fff; margin: 0; padding: 12px 16px; }
  h1 { font-size: 20px; margin: 0 0 4px; }
  .muted { color: var(--muted); }
  .errors { color: var(--hi); font-weight: 600; }
  .controls { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 10px 0; }
  .controls button { font-size: 16px; min-width: 38px; padding: 3px 8px; cursor: pointer; }
  #slider { flex: 1; min-width: 200px; }
  #event { font-weight: 600; min-height: 20px; margin: 4px 0 8px; }
  #stats { color: var(--muted); }
  svg { display: block; width: 100%; height: auto; background: #fff; }
  .legend span { display: inline-block; margin-right: 12px; }
  .legend i { display: inline-block; width: 14px; height: 14px; border: 1px solid #555; vertical-align: -2px; margin-right: 4px; }
  table.plan { border-collapse: collapse; margin-top: 10px; }
  table.plan td { padding: 2px 6px 2px 0; vertical-align: middle; }
  .sq { display: inline-block; width: 26px; height: 16px; margin-right: 2px; font-size: 9px; text-align: center;
        line-height: 16px; border: 1px solid #555; box-sizing: border-box; }
  .sq.pending { background: #fff !important; }
  .sq.track { outline: 2px solid var(--hi); }
  .sq.gone { opacity: 0.25; }
</style>
</head>
<body>
<h1>$title</h1>
<div id="summary" class="muted"></div>
<div id="result" class="muted"></div>
<div id="errors" class="errors"></div>
<div class="controls">
  <button id="first" title="first (Home)">&#x23EE;</button>
  <button id="back" title="step back (Left)">&#x25C0;</button>
  <button id="play" title="play / pause (Space)">&#x25B6;</button>
  <button id="fwd" title="step forward (Right)">&#x25B6;&#x7C;</button>
  <button id="last" title="last (End)">&#x23ED;</button>
  <input id="slider" type="range" min="0" value="0">
  <label>speed <select id="speed">
    <option value="1">1</option><option value="2">2</option><option value="5" selected>5</option>
    <option value="10">10</option><option value="25">25</option><option value="60">60</option>
  </select> events/s</label>
</div>
<div id="event"></div>
<div id="stats"></div>
<svg id="yard" xmlns="http://www.w3.org/2000/svg"></svg>
<div class="legend" id="legend"></div>
<table class="plan" id="plan"></table>
<script id="data" type="application/json">$data</script>
<script>
"use strict";
const D = JSON.parse(document.getElementById("data").textContent);
const K = D.trains.length, N = D.lanes;
const wagon = {};
D.trains.forEach((t, k) => t.forEach((w, p) => { wagon[(k + 1) + "." + (p + 1)] = { k: k + 1, p: p + 1, ...w }; }));
const fmt = x => (Math.round(x * 10) / 10).toString();

// Replay the plan: every train leaves as soon as it is complete and its predecessor has left.
function buildFrames() {
  const lanes = Array.from({ length: N }, () => []);
  const laneOf = {}, inBuffer = new Array(K).fill(0);
  let next = 1, loaded = 0, run = 0, lastGoods = null, track = [], trackTrain = null;
  const departed = [], frames = [];
  const snap = ev => frames.push({ ev, lanes: lanes.map(l => l.slice()), track: track.slice(), trackTrain,
    departed: departed.slice(), loaded, run, goods: lastGoods });
  snap({ kind: "start" });
  D.loads.forEach(([k, p, lane], i) => {
    const id = k + "." + p, w = wagon[id];
    if (w.goods !== lastGoods) { run++; lastGoods = w.goods; }
    lanes[lane - 1].push(id); laneOf[id] = lane; inBuffer[k - 1]++; loaded++;
    snap({ kind: "load", id, lane, step: i + 1 });
    while (next <= K && inBuffer[next - 1] === D.trains[next - 1].length) {
      trackTrain = next; track = [];
      for (let q = 1; q <= D.trains[next - 1].length; q++) {
        const wid = next + "." + q, l = laneOf[wid], at = lanes[l - 1].indexOf(wid);
        lanes[l - 1].splice(at, 1);
        track.push(wid);
        snap({ kind: "pull", id: wid, lane: l, train: next, blocked: at !== 0 });
      }
      departed.push(next);
      snap({ kind: "leave", train: next });
      track = []; trackTrain = null; next++;
    }
  });
  return frames;
}
const frames = buildFrames();

// ---- layout of the drawing
const ROW = 26, TOP = 56, WAG = 40, GAP = 3, SLOTS = 20;
const PORT_X = 10, PORT_W = 180, LANE_X = 290, LANE_W = SLOTS * (WAG + GAP) + 10;
const TRACK_X = LANE_X + LANE_W + 50, TRACK_W = 150;
const maxTrain = Math.max(...D.trains.map(t => t.length));
const HEIGHT = Math.max(TOP + N * ROW + 20, TOP + (maxTrain + 2) * 24 + 90, TOP + 16 * 24 + 40);
const WIDTH = TRACK_X + TRACK_W + 10;
const svg = document.getElementById("yard");
svg.setAttribute("viewBox", "0 0 " + WIDTH + " " + HEIGHT);
const NS = "http://www.w3.org/2000/svg";
function el(tag, attrs, text) {
  const e = document.createElementNS(NS, tag);
  for (const a in attrs) e.setAttribute(a, attrs[a]);
  if (text !== undefined) e.textContent = text;
  svg.appendChild(e);
  return e;
}
function car(id, x, y, w, h, hi) {
  const c = wagon[id];
  el("rect", { x, y, width: w, height: h, rx: 3, fill: D.colors[c.goods], stroke: hi ? "#d62828" : "#555",
               "stroke-width": hi ? 3 : 1 }).appendChild(document.createElementNS(NS, "title")).textContent =
    "wagon " + id + ": " + c.goods + ", " + fmt(c.weight) + " t";
  el("text", { x: x + w / 2, y: y + h / 2 + 4, "text-anchor": "middle", "font-size": 11, "pointer-events": "none" }, id);
}

function draw(i) {
  const f = frames[i], ev = f.ev;
  svg.textContent = "";
  // headings
  el("text", { x: PORT_X, y: 20, "font-size": 14, "font-weight": 700 }, "Port — loading track");
  el("text", { x: LANE_X, y: 20, "font-size": 14, "font-weight": 700 }, "Buffer — " + N + " FIFO lanes (enter left, leave right)");
  el("text", { x: TRACK_X, y: 20, "font-size": 14, "font-weight": 700 }, "Departure track");
  el("text", { x: PORT_X, y: 40, "font-size": 12, fill: "#666" },
     f.run ? "run " + f.run + " · " + f.goods + " · changes " + Math.max(f.run - 1, 0) : "nothing loaded yet");

  // port: the wagon just loaded and the next ones
  let y = TOP;
  if (ev.kind === "load") {
    el("text", { x: PORT_X, y: y + 12, "font-size": 12 }, "loaded → lane " + ev.lane);
    car(ev.id, PORT_X + 100, y, WAG + 20, ROW - 4, true);
  }
  y += ROW + 10;
  el("text", { x: PORT_X, y: y + 10, "font-size": 12, fill: "#666" }, "next to load:");
  y += 18;
  D.loads.slice(f.loaded, f.loaded + 15).forEach(([k, p, lane]) => {
    car(k + "." + p, PORT_X, y, WAG, ROW - 6, false);
    el("text", { x: PORT_X + WAG + 8, y: y + 14, "font-size": 11, fill: "#444" }, "→ lane " + lane);
    y += ROW - 2;
  });
  if (f.loaded + 15 < D.loads.length) el("text", { x: PORT_X, y: y + 12, "font-size": 11, fill: "#666" },
                                          "… " + (D.loads.length - f.loaded - 15) + " more");

  // buffer lanes: the front of the queue (oldest wagon) at the right end
  for (let l = 1; l <= N; l++) {
    const ly = TOP + (l - 1) * ROW, queue = f.lanes[l - 1];
    const weight = queue.reduce((s, id) => s + wagon[id].weight, 0);
    const active = ev.lane === l;
    el("rect", { x: LANE_X, y: ly, width: LANE_W, height: ROW - 4, fill: active ? "#fff3c4" : (l % 2 ? "#f6f6f6" : "#efefef"),
                 stroke: active ? "#d6b656" : "none" });
    el("text", { x: LANE_X - 70, y: ly + 15, "font-size": 11, "text-anchor": "end", fill: "#444" }, "lane " + l);
    const share = Math.min(weight / D.capacity, 1);
    el("rect", { x: LANE_X - 64, y: ly + 4, width: 56, height: ROW - 12, fill: "#fff", stroke: "#999" });
    el("rect", { x: LANE_X - 64, y: ly + 4, width: 56 * share, height: ROW - 12,
                 fill: share > 0.999 ? "#d62828" : share > 0.85 ? "#f4a261" : "#90be6d" });
    el("text", { x: LANE_X - 36, y: ly + 15, "font-size": 9, "text-anchor": "middle" }, fmt(weight) + " t");
    queue.slice(0, SLOTS).forEach((id, j) => {
      car(id, LANE_X + LANE_W - 5 - (j + 1) * (WAG + GAP), ly + 1, WAG, ROW - 6, id === ev.id);
    });
    if (queue.length > SLOTS) el("text", { x: LANE_X + 4, y: ly + 15, "font-size": 11 }, "+" + (queue.length - SLOTS));
  }
  el("text", { x: LANE_X + LANE_W + 6, y: TOP + 15, "font-size": 18, fill: "#999" }, "→");

  // departure track: the train under assembly, position 1 right behind the locomotive
  y = TOP;
  if (f.trackTrain) {
    el("rect", { x: TRACK_X, y, width: WAG + 40, height: ROW - 4, rx: 3, fill: "#4d4d4d" });
    el("text", { x: TRACK_X + (WAG + 40) / 2, y: y + 15, "font-size": 11, fill: "#fff", "text-anchor": "middle" },
       "T_" + f.trackTrain + " loco");
    f.track.forEach((id, q) => car(id, TRACK_X, y + (q + 1) * 24, WAG + 40, 20, id === ev.id));
    const n = D.trains[f.trackTrain - 1].length;
    el("text", { x: TRACK_X, y: y + (f.track.length + 1) * 24 + 16, "font-size": 12,
                 "font-weight": ev.kind === "leave" ? 700 : 400, fill: ev.kind === "leave" ? "#2a9d8f" : "#666" },
       ev.kind === "leave" ? "complete — leaves" : f.track.length + " of " + n + " wagons");
  } else {
    el("text", { x: TRACK_X, y: y + 14, "font-size": 12, fill: "#666" }, "empty");
  }
  el("text", { x: TRACK_X, y: HEIGHT - 24, "font-size": 12, fill: "#666" }, "left: " + (f.departed.length ? f.departed.map(k => "T_" + k).join(" ") : "—"));

  // texts below and above the drawing
  const describe = {
    start: () => "Start: the buffer is empty.",
    load: () => "Step " + ev.step + ": wagon " + ev.id + " (" + wagon[ev.id].goods + ", " + fmt(wagon[ev.id].weight) +
                " t) is loaded and goes to lane " + ev.lane + ".",
    pull: () => "T_" + ev.train + ": wagon " + ev.id + " is taken from the front of lane " + ev.lane + "." +
                (ev.blocked ? "  BLOCKED — it was not at the front!" : ""),
    leave: () => "T_" + ev.train + " is complete and leaves.",
  };
  document.getElementById("event").textContent = describe[ev.kind]();
  const inBuffer = f.lanes.reduce((s, q) => s + q.length, 0);
  document.getElementById("stats").textContent = "event " + i + " of " + (frames.length - 1) + " · loaded " + f.loaded +
    " of " + D.loads.length + " · in the buffer " + inBuffer + " · trains left " + f.departed.length + " of " + K;
  drawPlan(f);
  document.getElementById("slider").value = i;
}

// dispatch plan: every wagon as pending (white), in the buffer, on the track (red frame) or gone
function drawPlan(f) {
  const inLanes = new Set(f.lanes.flat()), onTrack = new Set(f.track), gone = new Set(f.departed);
  const rows = D.trains.map((t, k) => {
    const cells = t.map((w, p) => {
      const id = (k + 1) + "." + (p + 1);
      const state = gone.has(k + 1) ? "gone" : onTrack.has(id) ? "track" : inLanes.has(id) ? "buffer" : "pending";
      return '<span class="sq ' + state + '" style="background:' + D.colors[w.goods] + '" title="' + id + ": " +
             w.goods + ", " + fmt(w.weight) + ' t">' + (p + 1) + "</span>";
    }).join("");
    return "<tr><td><b>T_" + (k + 1) + "</b></td><td>" + cells + "</td></tr>";
  });
  document.getElementById("plan").innerHTML = "<tr><td colspan=2 class=muted>Dispatch plan — white: not loaded yet, " +
    "coloured: in the buffer, red frame: on the departure track, faded: left</td></tr>" + rows.join("");
}

// ---- controls
document.getElementById("summary").textContent = D.summary;
document.getElementById("result").textContent = D.result;
document.getElementById("errors").textContent = D.errors.length ? "Plan check failed: " + D.errors.join("; ") : "";
document.getElementById("legend").innerHTML = Object.entries(D.colors)
  .map(([g, c]) => '<span><i style="background:' + c + '"></i>' + g + "</span>").join("");
const slider = document.getElementById("slider");
slider.max = frames.length - 1;
let current = 0, timer = null;
const show = i => { current = Math.max(0, Math.min(frames.length - 1, i)); draw(current); };
function play(on) {
  clearInterval(timer); timer = null;
  document.getElementById("play").innerHTML = on ? "&#x23F8;" : "&#x25B6;";
  if (!on) return;
  if (current === frames.length - 1) show(0);
  timer = setInterval(() => { if (current >= frames.length - 1) play(false); else show(current + 1); },
                      1000 / Number(document.getElementById("speed").value));
}
document.getElementById("first").onclick = () => { play(false); show(0); };
document.getElementById("back").onclick = () => { play(false); show(current - 1); };
document.getElementById("fwd").onclick = () => { play(false); show(current + 1); };
document.getElementById("last").onclick = () => { play(false); show(frames.length - 1); };
document.getElementById("play").onclick = () => play(timer === null);
document.getElementById("speed").onchange = () => { if (timer) play(true); };
slider.oninput = () => { play(false); show(Number(slider.value)); };
document.addEventListener("keydown", e => {
  if (e.target.tagName === "SELECT") return;
  if (e.key === " ") { e.preventDefault(); play(timer === null); }
  else if (e.key === "ArrowRight") { play(false); show(current + 1); }
  else if (e.key === "ArrowLeft") { play(false); show(current - 1); }
  else if (e.key === "Home") { play(false); show(0); }
  else if (e.key === "End") { play(false); show(frames.length - 1); }
});
show(0);
</script>
</body>
</html>
""")
