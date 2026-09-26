"""Visualise games and training runs as self-contained HTML files.

    python scripts/visualize.py game                                  # agents/v8 vs avlod/best, seed 1
    python scripts/visualize.py game --a agents/v8/main.py --b starter --seed 7
    python scripts/visualize.py game --gen 12 --b agents/v8/main.py   # avlod_012 vs v8
    python scripts/visualize.py game --replay                         # + official Kaggle replay (~15 MB)
    python scripts/visualize.py episode 113630705.json                # a game downloaded from Kaggle
    python scripts/visualize.py progress                              # avlod/progress.html
    python scripts/visualize.py progress --dir avlod_v8

Agents: a path to main.py, or a built-in name (starter, random).
Output goes to replays/ (git-ignored) unless --out is given; add --open to open it in the browser.
"""
import argparse
import os
import sys
import webbrowser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from trainer import common as C  # noqa: E402
from trainer import viz  # noqa: E402


def _agent(spec, gen, avlod):
    if gen is not None:
        return os.path.join(ROOT, avlod, f"avlod_{gen:03d}", "main.py")
    if spec in C.BUILTIN:
        return spec
    return os.path.abspath(spec)


def _name(spec):
    if spec in C.BUILTIN:
        return spec
    rel = os.path.relpath(spec, ROOT)
    return os.path.dirname(rel).replace(os.sep, "/") or rel


def cmd_game(args):
    from kaggle_environments import make

    a = _agent(args.a, args.gen, args.avlod)
    b = _agent(args.b, None, args.avlod)
    for p in (a, b):
        if p not in C.BUILTIN and not os.path.exists(p):
            sys.exit(f"{p} not found")
    names = [_name(a), _name(b)]
    agents = [C.load_callable(C.read(p) if p not in C.BUILTIN else p) for p in (a, b)]
    if args.swap:
        agents, names = agents[::-1], names[::-1]
    env = make("kaggriculture", configuration={"seed": args.seed, "episodeSteps": args.steps})
    print(f"playing {names[0]} vs {names[1]} (seed {args.seed}) ...", flush=True)
    env.run(agents)
    last = env.steps[-1]
    for p in (0, 1):
        print(f"  {names[p]:<28} ${last[p].reward or 0:>10,.0f}  {last[p].status}")
    stem = args.out or os.path.join(ROOT, "replays", f"{names[0]}_vs_{names[1]}_seed{args.seed}".replace("/", "-"))
    stem = stem[:-5] if stem.endswith(".html") else stem
    out = viz.write(stem + ".html", viz.game_report(env, names, seed=args.seed))
    print(f"report  -> {os.path.relpath(out, ROOT)}")
    if args.replay:
        rp = viz.write(stem + ".replay.html", env.render(mode="html", width=1000, height=800))
        print(f"replay  -> {os.path.relpath(rp, ROOT)}  (official Kaggle visualizer)")
    if args.open:
        webbrowser.open("file://" + os.path.abspath(out))


class _Rec(dict):
    """dict with attribute access, so a Kaggle episode JSON looks like env.steps."""
    __getattr__ = dict.get


def cmd_episode(args):
    import json

    with open(args.file, encoding="utf-8") as f:
        ep = json.load(f)
    steps = [[_Rec(action=s.get("action"), reward=s.get("reward"), status=s.get("status"),
                   observation=s.get("observation") or {}) for s in row] for row in ep["steps"]]
    # public state (farms, market, town, day, hour) is stored with player 0 only on some exports
    for row in steps:
        o0 = row[0].observation
        for r in row[1:]:
            for k in ("farms", "market", "town", "day", "hour", "step"):
                if k in o0 and k not in r.observation:
                    r.observation[k] = o0[k]
    info = ep.get("info") or {}
    names = info.get("TeamNames") or ["player 0", "player 1"]
    env = _Rec(steps=steps)
    stem = args.out or os.path.join(ROOT, "replays", f"episode_{info.get('EpisodeId', 'kaggle')}")
    stem = stem[:-5] if stem.endswith(".html") else stem
    out = viz.write(stem + ".html", viz.game_report(env, names, seed=info.get("seed")))
    for p in (0, 1):
        print(f"  {names[p]:<28} ${ep['rewards'][p] or 0:>10,.0f}")
    print(f"report  -> {os.path.relpath(out, ROOT)}")
    if args.open:
        webbrowser.open("file://" + os.path.abspath(out))


def cmd_progress(args):
    d = os.path.join(ROOT, args.dir)
    out = viz.write(args.out or os.path.join(d, "progress.html"), viz.progress_report(d))
    print(f"progress -> {os.path.relpath(out, ROOT)}")
    if args.open:
        webbrowser.open("file://" + os.path.abspath(out))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("game", help="play one game and write an HTML report")
    g.add_argument("--a", default=os.path.join("agents", "v8", "main.py"), help="player 0 (default agents/v8/main.py)")
    g.add_argument("--b", default=os.path.join("avlod", "best", "main.py"), help="player 1 (default avlod/best/main.py)")
    g.add_argument("--gen", type=int, default=None, help="use avlod_NNN/main.py as player 0")
    g.add_argument("--avlod", default="avlod", help="folder of generations for --gen (e.g. avlod_v8)")
    g.add_argument("--seed", type=int, default=1)
    g.add_argument("--steps", type=int, default=720)
    g.add_argument("--swap", action="store_true", help="swap seats")
    g.add_argument("--replay", action="store_true", help="also write the official Kaggle replay HTML (~15 MB)")
    g.add_argument("--out", default=None, help="output path without .html")
    g.add_argument("--open", action="store_true")
    g.set_defaults(fn=cmd_game)
    e = sub.add_parser("episode", help="HTML report of an episode JSON downloaded from Kaggle")
    e.add_argument("file")
    e.add_argument("--out", default=None)
    e.add_argument("--open", action="store_true")
    e.set_defaults(fn=cmd_episode)
    p = sub.add_parser("progress", help="write the training-progress HTML of a generations folder")
    p.add_argument("--dir", default="avlod")
    p.add_argument("--out", default=None)
    p.add_argument("--open", action="store_true")
    p.set_defaults(fn=cmd_progress)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
