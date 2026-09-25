"""Checks that an agent satisfies the Kaggriculture submission rules.

Which agents are tested:
  * agents/base/main.py          - the evolvable template
  * avlod/best/main.py           - current best generation (if trained)
  * avlod/avlod_NNN/main.py      - the latest generation (if trained)
  * agents/v8/main.py            - your v8 (if present)
  * submission/main.py           - built by scripts/make_submission.py (if present)
Extra files can be added with:  KAGG_AGENTS=path1,path2 pytest tests/

Rules checked (from the competition page / kaggle_environments spec):
  - `main.py` at the root, the LAST callable in the file is the agent (Kaggle's loader)
  - only stdlib / numpy imports, no reading of repo files at runtime
  - every action is a dict {"farmer": [...], "hands": [[...]...], "market": [[...]...]}
    with known ops, one op per hired hand, <= maxMarketOrdersPerTurn market orders,
    JSON serialisable
  - a full 720-turn episode finishes with status DONE (no ERROR/TIMEOUT/INVALID) in both seats
  - per-turn time stays under actTimeout (1 s) - we require a safety margin
  - the agent beats the built-in "starter" baseline
"""
import ast
import glob
import json
import os
import subprocess
import sys
import tarfile
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kaggle_environments import make  # noqa: E402
from kaggle_environments.agent import get_last_callable  # noqa: E402

ACT_TIMEOUT = 1.0
SAFE_STEP_SECONDS = 0.5
MAX_ORDERS = 10
UNIT_OPS = {
    "NORTH", "SOUTH", "EAST", "WEST", "PASS", "PICKUP", "DROP", "PLANT", "WATER", "HARVEST",
    "FERTILIZE", "BUILD_COOP", "BUILD_PASTURE", "DIG", "PLACE", "FEED", "COLLECT_FERTILIZER", "CARE",
}
MARKET_OPS = {"BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL", "SELL", "HIRE", "BUY_LAND"}
ITEMS = {"WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL", "FERTILIZER", "GOOSE", "COW", "SHEEP"}
ALLOWED_IMPORTS = {
    "math", "random", "os", "sys", "json", "collections", "itertools", "heapq", "functools", "time",
    "copy", "typing", "dataclasses", "bisect", "statistics", "numpy", "operator", "enum", "re",
}


def _agent_files():
    files = [os.path.join(ROOT, "agents", "base", "main.py")]
    best = os.path.join(ROOT, "avlod", "best", "main.py")
    if os.path.exists(best):
        files.append(best)
    gens = sorted(glob.glob(os.path.join(ROOT, "avlod", "avlod_[0-9]*", "main.py")))
    if gens:
        files.append(gens[-1])
    for extra in (os.path.join(ROOT, "agents", "v8", "main.py"), os.path.join(ROOT, "submission", "main.py")):
        if os.path.exists(extra):
            files.append(extra)
    for extra in filter(None, os.environ.get("KAGG_AGENTS", "").split(",")):
        files.append(os.path.abspath(extra))
    return files


AGENTS = _agent_files()
IDS = [os.path.relpath(p, ROOT) for p in AGENTS]


def _load(path):
    with open(path, encoding="utf-8") as f:
        return get_last_callable(f.read(), path=path)


def validate_action(action, n_hands):
    assert isinstance(action, dict), f"action must be a dict, got {type(action)}"
    json.dumps(action)  # must be serialisable for the Kaggle runner
    assert set(action) <= {"farmer", "hands", "market"}, f"unknown keys {set(action)}"
    farmer = action.get("farmer", ["PASS"])
    assert isinstance(farmer, list) and farmer and farmer[0] in UNIT_OPS, f"bad farmer op {farmer}"
    hands = action.get("hands", [])
    assert isinstance(hands, list)
    assert len(hands) <= n_hands, f"{len(hands)} hand actions for {n_hands} hands"
    for h in hands:
        assert isinstance(h, list) and h and h[0] in UNIT_OPS, f"bad hand op {h}"
    for op in [farmer, *hands]:
        if op[0] in ("PICKUP", "PLACE", "PLANT"):
            assert len(op) >= 2 and op[1] in ITEMS, f"bad item in {op}"
        if len(op) >= 3:
            assert isinstance(op[2], int) and op[2] > 0, f"count must be positive int in {op}"
    market = action.get("market", [])
    assert isinstance(market, list)
    assert len(market) <= MAX_ORDERS, f"{len(market)} market orders > {MAX_ORDERS}"
    for o in market:
        assert isinstance(o, list) and o and o[0] in MARKET_OPS, f"bad market order {o}"
        if o[0] in ("BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL", "SELL"):
            assert len(o) == 3 and o[1] in ITEMS and isinstance(o[2], int) and o[2] > 0, f"bad order {o}"


class Recorder:
    """Wraps an agent: validates every action and records the time per turn."""

    def __init__(self, fn):
        self.fn, self.times, self.errors = fn, [], []

    def __call__(self, obs, config):
        t = time.perf_counter()
        a = self.fn(obs, config) if self.fn.__code__.co_argcount >= 2 else self.fn(obs)
        self.times.append(time.perf_counter() - t)
        try:
            validate_action(a, len(obs["farms"][obs["player"]]["hands"]))
        except AssertionError as e:
            self.errors.append((obs["step"], str(e)))
        return a


def _game(path, opponent, seed, seat):
    rec = Recorder(_load(path))
    agents = [rec, opponent] if seat == 0 else [opponent, rec]
    env = make("kaggriculture", configuration={"seed": seed})
    env.run(agents)
    return env, rec


# ---------------------------------------------------------------- static checks
@pytest.mark.parametrize("path", AGENTS, ids=IDS)
def test_file_is_valid_submission(path):
    assert os.path.basename(path) == "main.py"
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    # Kaggle takes the LAST callable defined at module level as the agent
    fn = _load(path)
    assert callable(fn)
    assert fn.__name__ == "agent", f"last callable is {fn.__name__!r}, Kaggle would call it instead of agent()"
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            mods = [(node.module or "").split(".")[0]]
        else:
            continue
        for m in mods:
            assert m in ALLOWED_IMPORTS, f"import {m!r} may not exist on the Kaggle runner"
    assert os.path.getsize(path) < 5 * 1024 * 1024


@pytest.mark.parametrize("path", AGENTS, ids=IDS)
def test_runs_standalone_outside_repo(path, tmp_path):
    """The file must work alone (Kaggle only receives main.py)."""
    dst = tmp_path / "main.py"
    dst.write_text(open(path, encoding="utf-8").read(), encoding="utf-8")
    code = (
        "from kaggle_environments import make\n"
        "env = make('kaggriculture', configuration={'seed': 7, 'episodeSteps': 96})\n"
        "env.run(['main.py', 'random'])\n"
        "s = env.steps[-1]\n"
        "assert s[0].status == 'DONE', s[0].status\n"
        "print(s[0].reward)\n"
    )
    r = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]


# ---------------------------------------------------------------- full episodes
@pytest.mark.parametrize("path", AGENTS, ids=IDS)
@pytest.mark.parametrize("seat", [0, 1])
def test_full_episode_vs_random(path, seat):
    env, rec = _game(path, "random", seed=100 + seat, seat=seat)
    last = env.steps[-1]
    assert len(env.steps) == 720
    assert last[seat].status == "DONE", f"status {last[seat].status}"
    assert not rec.errors, f"invalid actions: {rec.errors[:5]}"
    assert max(rec.times) < SAFE_STEP_SECONDS, f"slowest turn {max(rec.times):.3f}s (actTimeout {ACT_TIMEOUT}s)"
    assert last[seat].reward > last[1 - seat].reward


@pytest.mark.parametrize("path", AGENTS, ids=IDS)
def test_beats_starter(path):
    wins = 0
    for seed, seat in ((11, 0), (12, 1)):
        env, rec = _game(path, "starter", seed=seed, seat=seat)
        last = env.steps[-1]
        assert last[seat].status == "DONE"
        assert not rec.errors, f"invalid actions: {rec.errors[:5]}"
        wins += last[seat].reward > last[1 - seat].reward
    assert wins == 2


def test_self_play_is_stable():
    """Two copies of the best agent must not share state (Kaggle runs them in separate processes)."""
    path = AGENTS[1] if len(AGENTS) > 1 else AGENTS[0]
    a, b = Recorder(_load(path)), Recorder(_load(path))
    env = make("kaggriculture", configuration={"seed": 5})
    env.run([a, b])
    last = env.steps[-1]
    assert [s.status for s in last] == ["DONE", "DONE"]
    assert not a.errors and not b.errors
    assert min(s.reward for s in last) > 3000  # both make money


def test_v8_is_beaten_by_best():
    v8 = os.path.join(ROOT, "agents", "v8", "main.py")
    best = os.path.join(ROOT, "avlod", "best", "main.py")
    if not (os.path.exists(v8) and os.path.exists(best)):
        pytest.skip("needs agents/v8/main.py and a trained avlod/best/main.py")
    score = 0.0
    for seed, seat in ((21, 0), (22, 1), (23, 0), (24, 1)):
        env, _ = _game(best, _load(v8), seed=seed, seat=seat)
        me, opp = env.steps[-1][seat].reward, env.steps[-1][1 - seat].reward
        score += 1.0 if me > opp else 0.5 if me == opp else 0.0
    assert score >= 2.5, f"best generation scored {score}/4 vs v8"


def test_submission_archive():
    tar = os.path.join(ROOT, "submission", "submission.tar.gz")
    if not os.path.exists(tar):
        pytest.skip("run scripts/make_submission.py first")
    with tarfile.open(tar) as t:
        names = t.getnames()
    assert "main.py" in names, f"main.py must be at the archive root, got {names}"
