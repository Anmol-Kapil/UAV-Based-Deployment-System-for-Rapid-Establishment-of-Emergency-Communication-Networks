# UAV-Based Deployment System for Rapid Establishment of Emergency Communication Networks

Software prototype: custom GCS → coverage/candidate/scoring engine → MAVLink →
ArduPilot SITL → Gazebo. No onboard companion computer; the flight controller
handles stabilization/navigation, the operator has manual override, and final
node deployment is manual.

Built incrementally, phase by phase. **Phases 1–5 are implemented so far.**

The Gazebo/ArduPilot SITL simulation environment (`simulation/README.md`) is
also documented now, ahead of schedule — it's independent infrastructure
setup, not backend code, so it doesn't jump the phase queue. It gets you a
running, MAVLink-heartbeating SITL+Gazebo instance ready for whenever
Phase 6 onward needs it.

## Phase roadmap

| Phase | Scope | Status |
|---|---|---|
| 1 | Map + affected-area polygon drawing | ✅ Done |
| 2 | Virtual nodes + coverage analysis | ✅ Done |
| 3 | Candidate generation | ✅ Done |
| 4 | Candidate scoring + top-2 locations | ✅ Done |
| 5 | FastAPI backend | ✅ Done |
| 6 | pymavlink connection | Not started |
| 7 | Live telemetry | Not started |
| 8 | GPS target command | Not started |
| 9 | Gazebo flight | Not started |
| 10 | Virtual deployment simulation | Not started |

## Phase 1 — what was implemented

**Files added/changed:**
- `frontend/index.html` — page layout: map pane, right-side control panel, bottom mission log
- `frontend/style.css` — dark control-room visual theme (see design notes below)
- `frontend/app.js` — Leaflet map init (with schematic fallback if tiles don't load), polygon drawing, node/coverage-circle rendering, UI state wiring, log panel
- `data/nodes.json` — 3 predefined synthetic existing-node locations
- `backend/config.py` — configuration constants for later phases (not used yet)
- `requirements.txt` — placeholder; Phase 1 needs no Python dependencies

**What it does:**
1. Opens a Leaflet map centered on the synthetic test scenario (falls back to a schematic coordinate grid if OpenStreetMap tiles can't be reached — drawing and future analysis don't depend on map imagery).
2. Displays the 3 predefined communication nodes from `data/nodes.json`, each with its coverage-radius circle.
3. **Draw Affected Area** — click to start drawing, click points on the map to add polygon vertices, then either click **Finish Area** or click back near the first vertex to close the polygon.
4. **Clear Area** — resets the drawing and re-enables drawing from scratch.
5. **Analyze Area** — disabled until a valid (≥3-point) closed polygon exists. Enabling it doesn't run real analysis yet — clicking it logs that the coverage engine arrives in Phase 2, so the flow is visibly wired end to end without pretending to compute something it can't yet.
6. A status panel tracks drawing state (IDLE / DRAWING / AREA DEFINED), point count, and node count. A mission log panel timestamps every action.
7. The right panel also shows placeholder "Recommended Locations" and "Mission / UAV Status" sections, dimmed and labeled with the phase that will implement them — so the final panel layout is visible now without any of that logic existing yet.

**What it deliberately does *not* do:** no backend, no coverage math, no candidate generation/scoring, no MAVLink, no Gazebo. Those are later phases.

### Design notes

The look is a dark technical control-room theme, not a marketing page: near-black
background, amber accent for planning/drawing state (the polygon and the phase
indicator), green for existing infrastructure (nodes and coverage circles) — so
color alone tells you "what exists" (green) vs. "what you're defining" (amber).
Data readouts (stats, log timestamps) use a monospace face; labels and buttons
use a plain sans. The schematic fallback grid means the tool stays fully usable
if map tiles aren't reachable, which matters for a field/offline-leaning tool.

## Phase 2 — what was implemented

**Files added:**
- `backend/coverage.py` — Haversine distance, ray-casting point-in-polygon test, grid generation over a polygon's bounding box, and `compute_coverage()` which classifies each grid point as covered or a gap against the node list
- `backend/tests/test_coverage.py` — 13 unit tests covering distance math, point-in-polygon (inside/outside/degenerate), coverage percentage math, missing-radius fallback, and invalid input (too-few-point polygon, empty polygon, no nodes)

**What it does:** samples the affected-area polygon as a grid (spacing set by `GRID_RESOLUTION_M` in `config.py`, default 20 m), and for every grid point checks whether any existing node's coverage radius reaches it (Haversine distance ≤ radius). Points that are inside the polygon but out of range of every node are gap points. Coverage % and gap % always sum to 100 and never divide by zero — a degenerate polygon (fewer than 3 points, or one too small to contain any grid point) returns 0%/0% rather than crashing.

**Still not wired up:** this is a standalone Python module, not yet reachable from the GCS. The frontend's Analyze Area button still shows the Phase 2 placeholder message — hooking it up to real numbers happens once FastAPI exists (Phase 5). Candidate generation, scoring, and the "coverage improvement from a virtual node" calculation are Phases 3–4, not this one.

### How to run

```bash
cd backend
python3 coverage.py
```

This loads `data/nodes.json` and runs coverage analysis against a small
built-in demo polygon (a triangle straddling one of the 3 nodes, chosen
so the demo shows a realistic mix of covered and gap points, not 0% or
100%). Expected output:

```
Grid points sampled : 351
Covered             : 297
Gap                 : 54
Coverage %          : 84.6
Gap %               : 15.4
```

### How to test

```bash
cd backend
python3 -m unittest tests.test_coverage -v
```

Expected result: `Ran 13 tests ... OK`, no failures.

## Phase 3 — what was implemented

**Files added:**
- `backend/candidate_generator.py` — connected-component clustering of coverage-gap points (8-connected grid adjacency, using the same lattice `compute_coverage()` sampled), one candidate per cluster (centroid, or nearest actual gap point if the centroid itself falls outside the polygon), and a splitting step that keeps dividing the largest clusters until at least 5 candidates exist
- `backend/tests/test_candidate_generator.py` — 8 unit tests covering clustering (contiguous points merge, size-sorted output, no-gap case), candidate placement (inside polygon, distinct coordinates), the "at least 5" guarantee, full-coverage (zero candidates) and degenerate-polygon edge cases

**Also changed:** `backend/coverage.py`'s `generate_grid()` now steps by index (`lat = min_lat + i*step_lat`) instead of repeated `+=` accumulation, and a new `grid_parameters()` helper exposes the lattice's origin/step/size. Both are needed so clustering can recover each gap point's exact `(row, col)` grid index without floating-point drift — this doesn't change `generate_grid()`'s inputs/outputs, and all 13 Phase 2 tests still pass against it.

**What it does:** runs Phase 2's coverage analysis, groups the resulting gap points into clusters using 8-connected grid adjacency (not raw distance — two points are neighbors only if they're adjacent cells on the sampled lattice), and proposes the centroid of each cluster as a candidate deployment site. If fewer than 5 distinct clusters exist, the largest cluster(s) get split along their longer geographic axis (still real gap points, nothing fabricated) until 5 candidates are reached — or until there simply isn't enough gap area left to split further, in which case it honestly returns fewer than 5 rather than padding with meaningless duplicates.

**Still not wired up:** no scoring or ranking yet (Phase 4) — this module proposes candidates but doesn't judge between them. Still not reachable from the GCS (Phase 5/FastAPI).

### How to run

```bash
cd backend
python3 candidate_generator.py
```

Loads `data/nodes.json` and runs against a built-in irregular hexagon
polygon (deliberately non-triangular, so it produces more than one gap
cluster). Expected output — exact coordinates may shift slightly run to
run only if you change the demo polygon/nodes, but with the shipped demo
data you should get exactly 5 candidates:

```
Candidates generated: 5
  Candidate 1: lat=13.08294, lon=80.27255, source cluster size=6922
  Candidate 2: lat=13.08307, lon=80.26844, source cluster size=3461
  Candidate 3: lat=13.08282, lon=80.27666, source cluster size=3461
  Candidate 4: lat=13.08715, lon=80.26851, source cluster size=1731
  Candidate 5: lat=13.08629, lon=80.27674, source cluster size=1731
```

### How to test

```bash
cd backend
python3 -m unittest tests.test_candidate_generator -v
```

Expected result: `Ran 8 tests ... OK`. To confirm Phase 2 wasn't broken
by the `coverage.py` changes, run both suites together:

```bash
python3 -m unittest discover -s tests -v
```

Expected result: `Ran 21 tests ... OK`.

## Phase 4 — what was implemented

**Files added:**
- `backend/scoring.py` — `distance_to_polygon_boundary_m()` (point-to-segment planar distance to the nearest polygon edge) and `score_candidates()`, which scores every Phase 3 candidate on three normalized 0–100 criteria and combines them into a single weighted score; `top_n()` slices the top-scoring candidates off an already-ranked list
- `backend/tests/test_scoring.py` — 13 unit tests covering the boundary-distance geometry (center vs. near-edge vs. on-vertex, degenerate polygon), score-field completeness, 0–100 normalization bounds, descending rank order, distance-preference direction, weight configurability, and the zero-coverage-improvement edge case

**What it does:** for each candidate from Phase 3, computes three raw signals and normalizes each to 0–100 relative to the candidate batch:
1. **Coverage improvement** — a virtual node is temporarily added at the candidate's location (a copy of the node list, so `nodes` itself is never mutated), Phase 2's `compute_coverage()` is re-run, and the improvement is `new_coverage% − current_coverage%`.
2. **Distance suitability** — Haversine distance from the candidate to `UAV_HOME_LAT`/`UAV_HOME_LON` (in `config.py`), inverted so the closest candidate scores 100.
3. **Deployment suitability** — planar point-to-segment distance from the candidate to the nearest edge of the affected-area polygon, so a solidly-interior site scores higher than one hugging the boundary.

The three normalized scores are combined as `score = COVERAGE_WEIGHT*coverage_score + DISTANCE_WEIGHT*distance_score + SUITABILITY_WEIGHT*suitability_score` (0.60 / 0.25 / 0.15 by default, all configurable in `config.py`), candidates are sorted descending by score, and `top_n()` returns the top two — the two locations Stage 1's demo scenario is meant to recommend.

This is a transparent, deterministic multi-criteria formula, not a learned or opaque model — every number feeding a candidate's score is traceable back to a concrete calculation (a coverage percentage, a distance in meters), which is the point: an operator should be able to see *why* a location was recommended.

**Still not wired up:** no FastAPI yet (Phase 5) — this module scores whatever candidate list it's handed, but nothing yet calls it from the GCS. `mission_manager.py`, GPS target conversion, and everything MAVLink/Gazebo-related remain Phases 5 onward.

### How to run

```bash
cd backend
python3 scoring.py
```

Loads `data/nodes.json`, runs Phase 3's candidate generation against the
same irregular hexagon demo polygon, then scores and ranks the result.
Expected output (exact scores depend on the demo polygon/nodes, but with
the shipped demo data you should see 5 candidates scored and the same
top 2 called out separately):

```
Candidates scored: 5
  #1  lat=13.08715 lon=80.26851  score=73.3  (coverage+=6.3pp, dist_home=549m, boundary=382m)
  #2  lat=13.08282 lon=80.27666  score=73.1  (coverage+=6.3pp, dist_home=646m, boundary=579m)
  #3  lat=13.08294 lon=80.27255  score=63.5  (coverage+=3.2pp, dist_home=202m, boundary=919m)
  #4  lat=13.08307 lon=80.26844  score=61.4  (coverage+=3.8pp, dist_home=248m, boundary=514m)
  #5  lat=13.08629 lon=80.27674  score=56.2  (coverage+=5.2pp, dist_home=767m, boundary=386m)

Top 2 recommended locations:
  Location A: lat=13.08715, lon=80.26851, score=73.3
  Location B: lat=13.08282, lon=80.27666, score=73.1
```

### How to test

```bash
cd backend
python3 -m unittest tests.test_scoring -v
```

Expected result: `Ran 13 tests ... OK`. To confirm Phases 2–3 weren't
broken, run every suite together:

```bash
python3 -m unittest discover -s tests -v
```

Expected result: `Ran 34 tests ... OK`.

## Phase 5 — what was implemented

**Files added:**
- `backend/database.py` — SQLite persistence: `nodes`, `missions`, `telemetry`, `deployments` tables (schema for all four, per the spec, but only `nodes` and `missions` are actually written to yet — `telemetry`/`deployments` stay correctly-shaped but empty until Phases 7 and 10 populate them), seeding `nodes` from `data/nodes.json` on first run
- `backend/models.py` — Pydantic request/response schemas for every endpoint
- `backend/main.py` — the FastAPI app: wires Phases 2–4 behind HTTP endpoints, serves the frontend and `data/` as static files so the whole app runs from one origin/port, and hosts a `/ws/telemetry` WebSocket stub
- `backend/tests/test_api.py` — 23 tests using FastAPI's `TestClient` (in-process, no real socket) covering the happy path end-to-end (area → analyze → candidates → select-target → mission/generate → persisted in `/api/missions`), every documented error case (no area, too few points, target outside the area, target too close to an existing node, candidates requested before analyze), the honest 501 stubs, and static file serving

**Also changed:**
- `frontend/app.js` — **Analyze Area** now calls the real backend (`POST /api/area` → `POST /api/analyze` → `GET /api/candidates`) instead of showing the Phase 1 placeholder message. Renders real coverage/gap percentages, a downsampled gap/covered-point overlay on the map (see note below), and candidate + top-2 markers. Adds `selectLocation()` (wired to new **Select A/B** buttons in the Recommended Locations panel → `POST /api/select-target`) and `generateMission()`/`sendTarget()` (wired to the new Mission panel → `POST /api/mission/generate`, `POST /api/mission/send`)
- `frontend/index.html` — Recommended Locations panel now renders real candidate cards instead of a static placeholder; added the Mission panel (target lat/lon/altitude fields, Generate Mission / Send Target buttons, mission-state stat)
- `frontend/style.css` — styles for the new location cards and mission form fields
- `backend/config.py` — added `MIN_NODE_SEPARATION_M` (target-too-close-to-a-node validation)
- `requirements.txt` — `fastapi`, `uvicorn`, `httpx` uncommented/added (httpx is only needed for `TestClient` in the test suite)

**What it does:** exposes the API surface from the spec as far as Phases 2–4 support it:

| Endpoint | Behavior |
|---|---|
| `GET /api/status` | current mission state, whether an area/analysis exists, `uav_connected: false` (honest — no MAVLink yet) |
| `GET /api/nodes` | the 3 existing nodes, seeded into SQLite from `data/nodes.json` |
| `POST /api/area` | stores the drawn polygon; a new area invalidates any prior analysis/candidates/target |
| `POST /api/analyze` | runs Phase 2's `compute_coverage()` against the stored area; 400 if no area yet |
| `GET /api/candidates` | runs Phase 3 + Phase 4 (`generate_candidates()` → `score_candidates()`) against the last analysis; 400 if `/api/analyze` hasn't been run |
| `POST /api/select-target` | validates the point is inside the affected area and not within `MIN_NODE_SEPARATION_M` of an existing node; records it as the selected target |
| `POST /api/mission/generate` | validates and persists a mission row (target, altitude, the candidate's score if it matches one) to SQLite, status `MISSION_READY` |
| `POST /api/mission/send`, `POST /api/mission/abort` | **honest 501** — these need the Phase 6 MAVLink connection to mean anything; the response names the required phase instead of pretending to control a UAV that doesn't exist |
| `POST /api/deployment/simulate` | **honest 501** — Phase 10 |
| `GET /api/missions` | all persisted missions, newest first |
| `GET /api/deployments` | always `[]` for now — the table exists (so this is "no deployments yet", not "not implemented") but nothing writes to it until Phase 10 |
| `WS /ws/telemetry` | accepts the connection, immediately sends `{"implemented": false, "phase_required": 7, ...}`, then closes — reachable now, honest about not streaming real telemetry yet |

**Map rendering note:** the affected-area demo polygon samples into thousands of grid points (e.g. ~7,800 for the Phase 3/4 demo hexagon, ~6,900 of them gap points). Rendering one Leaflet marker per point would noticeably lag the browser, so the on-map gap/covered-point overlay is downsampled to at most 400 points per layer for display only — every percentage in the stats panel and every score in the Recommended Locations panel is still computed over the full, non-downsampled grid server-side.

**Still not wired up:** no MAVLink connection (Phase 6), so `/api/mission/send` and `/api/mission/abort` can't actually do anything yet — they say so. No live telemetry (Phase 7). No Gazebo (Phase 9). No deployment simulation (Phase 10).

### How to run

Phase 5 replaces the plain static file server with the FastAPI app, which now serves the frontend itself — one process, one port, no CORS to configure.

```bash
cd uav-emergency-deployment/backend
pip install -r ../requirements.txt
python3 -m uvicorn main:app --reload
```

Then open:

```
http://localhost:8000/
```

(`/` redirects to `/frontend/index.html`, so the "just open the root port" convenience mentioned in Phase 1's instructions now actually exists rather than being aspirational.) Draw an affected area, click **Analyze Area**, and the coverage %, gap %, candidate markers, and top-2 Recommended Locations cards are all real, backend-computed numbers. Selecting a location and clicking **Generate Mission** persists a mission to `data/uav_emergency.db`; clicking **Send Target** logs the honest "MAVLink arrives in Phase 6" response instead of pretending to fly anywhere.

The Phase 2–4 standalone demos (`python3 coverage.py`, `python3 candidate_generator.py`, `python3 scoring.py`) still work exactly as before — Phase 5 wires those modules into the API, it doesn't change them.

### How to test

```bash
cd backend
python3 -m unittest tests.test_api -v
```

Expected result: `Ran 23 tests ... OK`. Full suite across every phase:

```bash
python3 -m unittest discover -s tests -v
```

Expected result: `Ran 57 tests ... OK`.

Manual check: with the server running, `GET http://localhost:8000/api/status` should return `{"status": "ok", "phase": 5, ...}`, and `POST /api/mission/send` should return HTTP 501 with a message naming Phase 6 — not a crash, not a fake success.

## How to run

Phase 1 is a static frontend with no backend yet, so any static file server
works — but the server must be started **from inside this folder**
(`uav-emergency-deployment/`, the one that directly contains `frontend/`,
`data/`, `backend/`), not from its parent.

```bash
cd uav-emergency-deployment
python -m http.server 8000
```

Then open:

```
http://localhost:8000/frontend/index.html
```

or just `http://localhost:8000/` — a root `index.html` redirects there
automatically, so it also works if you (or a teammate) forget the
`/frontend/` part.

**If you see `GET /frontend/index.html 404`** in the server's terminal output,
the server was started one level too high — e.g. from `Downloads\PJT1` when
the actual `frontend/` folder is at `Downloads\PJT1\uav-emergency-deployment\frontend`.
Stop the server (Ctrl+C), `cd` one level down into `uav-emergency-deployment`,
and restart it there.

(Opening `index.html` directly via `file://` will work for the map itself, but
`fetch("../data/nodes.json")` will be blocked by the browser's CORS rules for
local files — the app falls back to built-in node data in that case and logs
that it did so, but serving over HTTP is the intended way to run it.)

Phases 2–4 are still runnable as standalone Python modules (see each phase's
section above) — Phase 5 wires them into the FastAPI app without changing
them. To run the full app (frontend + backend together), use the Phase 5
instructions above (`uvicorn main:app`) instead of the plain `http.server`
command below, which now only serves static files with no working
Analyze/Candidates/Mission flow behind them.

## How to test

Manual test checklist (frontend, Phase 1 — no backend involved):

1. Load the page — confirm 3 green nodes with dashed coverage circles appear, and the log shows "GCS initialized".
2. Click **Draw Affected Area** — button should show "Drawing…" and become highlighted; **Clear Area** becomes enabled.
3. Click 4–5 points on the map — confirm amber vertex markers and a connecting dashed line appear, and "Polygon Points" updates live.
4. After 3+ points, click **Finish Area** (or click back near the first vertex) — confirm the polygon closes into a filled amber area, drawing controls disable, and **Analyze Area** becomes enabled.
5. Click **Analyze Area** — confirm a log line says the coverage engine isn't implemented yet (Phase 2). Nothing should crash or silently pretend to produce results.
6. Click **Clear Area** — confirm the polygon, vertices, and line are all removed, stats reset to `--`/`0`, and **Draw Affected Area** is re-enabled.
7. Try disconnecting from the internet before loading the page (or block `tile.openstreetmap.org`) — confirm the schematic fallback grid appears with its banner, and that drawing/finishing/clearing still work normally on it.

Automated tests (backend, Phases 2–5):

```bash
cd backend
python3 -m unittest discover -s tests -v
```

Expected result: `Ran 57 tests ... OK`.

## Expected result

A working, honest Phase 1–5: you can define an affected area on a map over a
synthetic 3-node scenario, and the **Analyze Area** button now runs real
coverage analysis, real candidate generation, and real scoring through the
FastAPI backend — the Recommended Locations panel shows genuine top-2 sites
with real scores, selecting one and generating a mission persists it to
SQLite, and every endpoint that would need MAVLink or Gazebo to mean
anything (`mission/send`, `mission/abort`, `deployment/simulate`, live
telemetry) honestly reports which future phase implements it instead of
faking a result. Nothing about MAVLink, ArduPilot SITL, or Gazebo is
implemented — that starts at Phase 6.
