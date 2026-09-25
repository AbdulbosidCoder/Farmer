"""Shared helpers: loading agents exactly like Kaggle does, rendering PARAMS, playing games."""
import ast
import json
import os
import pprint
import random
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AVLOD_DIR = os.path.join(ROOT, "avlod")
BASE_AGENT = os.path.join(ROOT, "agents", "base", "main.py")
V8_AGENT = os.path.join(ROOT, "agents", "v8", "main.py")

BEGIN = "# === PARAMS BEGIN ==="
END = "# === PARAMS END ==="

BUILTIN = ("starter", "random", "pass")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def extract_params(src):
    """Return the PARAMS dict literal defined in an agent source (or None)."""
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "PARAMS" for t in node.targets):
            try:
                return dict(ast.literal_eval(node.value))
            except ValueError:
                return None
    return None


def extract_bounds(src):
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "PARAM_BOUNDS" for t in node.targets):
            try:
                return {k: tuple(v) for k, v in ast.literal_eval(node.value).items()}
            except ValueError:
                return None
    return None


def render(src, params):
    """Return agent source with PARAMS replaced by `params`.

    Uses the BEGIN/END markers when present; otherwise appends a PARAMS.update()
    right before the final `def agent` so `agent` stays the last callable."""
    body = "PARAMS = " + pprint.pformat({k: _clean(v) for k, v in params.items()}, sort_dicts=False, width=100)
    if BEGIN in src and END in src:
        a = src.index(BEGIN) + len(BEGIN)
        b = src.index(END)
        return src[:a] + "\n" + body + "\n" + src[b:]
    upd = "PARAMS.update(" + pprint.pformat({k: _clean(v) for k, v in params.items()}, sort_dicts=False) + ")\n\n\n"
    idx = src.rfind("\ndef agent")
    if idx < 0:
        return src + "\n" + upd
    return src[: idx + 1] + upd + src[idx + 1 :]


def _clean(v):
    if isinstance(v, float):
        return round(v, 4)
    return v


def load_callable(src_or_name):
    """Build an agent callable the same way kaggle_environments does for main.py files."""
    if src_or_name in BUILTIN:
        return src_or_name
    from kaggle_environments.agent import get_last_callable

    return get_last_callable(src_or_name)


def play(src_a, src_b, seed, steps=720):
    """Play one full game; returns dict with rewards/statuses/timing."""
    from kaggle_environments import make

    a = load_callable(src_a)
    b = load_callable(src_b)
    env = make("kaggriculture", configuration={"seed": int(seed), "episodeSteps": steps})
    t0 = time.time()
    env.run([a, b])
    last = env.steps[-1]
    return {
        "rewards": [s.reward for s in last],
        "statuses": [s.status for s in last],
        "seconds": time.time() - t0,
    }


def play_job(job):
    """Pool worker entry: job = (key, src_a, src_b, seed)."""
    key, src_a, src_b, seed = job
    random.seed(seed)
    try:
        r = play(src_a, src_b, seed)
    except Exception as e:  # never kill the whole generation
        r = {"rewards": [None, None], "statuses": ["ERROR", "ERROR"], "error": repr(e)}
    return key, r


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
