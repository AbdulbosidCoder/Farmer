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


def _number_node(node):
    """Value of an int/float literal (also `-5`), else None. Booleans are not numbers here."""
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        v = _number_node(node.operand)
        return None if v is None else (-v if isinstance(node.op, ast.USub) else v)
    if isinstance(node, ast.Constant) and not isinstance(node.value, bool) and isinstance(node.value, (int, float)):
        return node.value
    return None


def _constant_nodes(src):
    """Top-level `NAME = <number>` assignments -> {name: value node}.

    Agents like agents/v8/main.py keep their knobs as plain module constants
    instead of a PARAMS dict; these are what the trainer evolves for them."""
    out = {}
    for node in ast.parse(src).body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and node.targets[0].id.isupper()
                and _number_node(node.value) is not None):
            out[node.targets[0].id] = node.value
    return out


def extract_constants(src):
    """Numeric module-level constants of an agent without a PARAMS dict."""
    return {k: _number_node(v) for k, v in _constant_nodes(src).items()}


def load_sidecar_bounds(agent_path):
    """`bounds.json` next to the agent: {"NAME": [min, max], ...} (keeps main.py untouched)."""
    path = os.path.join(os.path.dirname(os.path.abspath(agent_path)), "bounds.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {k: tuple(v) for k, v in raw.items() if not k.startswith("_")}


def render_constants(src, params):
    """Return agent source with the literal values of module constants replaced.

    Only the number itself is rewritten (comments and the rest of the line stay),
    and a constant that was an int in the source stays an int - v8 uses them for
    slicing/ranges, where a float would raise."""
    nodes = _constant_nodes(src)
    lines = src.splitlines(keepends=True)
    edits = []
    for k, v in params.items():
        node = nodes.get(k)
        if node is None or node.lineno != node.end_lineno:
            continue
        orig = _number_node(node)
        v = int(round(v)) if isinstance(orig, int) else round(float(v), 4)
        if v == orig:
            continue  # unchanged value keeps its original spelling (0.60, 999999, ...)
        edits.append((node.lineno - 1, node.col_offset, node.end_col_offset, repr(v)))
    # bytes offsets: ast columns are UTF-8 byte offsets
    for ln, a, b, text in sorted(edits, reverse=True):
        raw = lines[ln].encode("utf-8")
        lines[ln] = (raw[:a] + text.encode("utf-8") + raw[b:]).decode("utf-8")
    return "".join(lines)


def render(src, params):
    """Return agent source with PARAMS replaced by `params`.

    Uses the BEGIN/END markers when present; for an agent without a PARAMS dict
    (plain module constants, like v8) rewrites the constants in place; otherwise
    appends a PARAMS.update() right before the final `def agent` so `agent` stays
    the last callable."""
    if not (BEGIN in src and END in src) and extract_params(src) is None:
        return render_constants(src, params)
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
