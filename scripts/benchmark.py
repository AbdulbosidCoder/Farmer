"""Benchmark agents on every map size and against a recorded Kaggle opponent.

Map sizes (the farm grows by quadrants; NW is always open, land is bought in the
order NE, SW, SE):
    5x5          NW only                (0 land buys)
    5x10         NW + NE                (1)
    5x10+5x5     NW + NE + SW           (2)
    10x10        all four quadrants     (3)
For each size the agent is forced to buy exactly that much land as early as it
can afford it, so the result shows how well it uses a farm of that size.

    python scripts/benchmark.py maps --agents avlod/best/main.py agents/v9/main.py
    python scripts/benchmark.py ghost episode.json --agents agents/v9/main.py
    python scripts/benchmark.py duel agents/v9/main.py avlod/best/main.py --seeds 20

`ghost` replays the other player of a downloaded Kaggle episode move by move on
the same seed - the closest offline stand-in for the opponent you lost to.
"""
import argparse
import json
import os
import statistics
import sys
from multiprocessing import Pool

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from trainer import common as C  # noqa: E402

MAPS = [(0, "5x5"), (1, "5x10"), (2, "5x10+5x5"), (3, "10x10")]


with_land = C.force_land


def _play(job):
    key, a, b, seed = job
    return key, C.play_job((None, a, b, seed))[1]


def _ghost_agent(path, seat):
    with open(path, encoding="utf-8") as f:
        steps = json.load(f)["steps"]
    acts = [steps[t][seat].get("action") or {} for t in range(len(steps))]

    def ghost(obs):
        t = int(obs["step"]) + 1 if "step" in obs else int(obs["day"]) * 24 + int(obs["hour"]) + 1
        return acts[t] if t < len(acts) else {"farmer": ["PASS"], "hands": [], "market": []}
    return ghost


def _pool(n):
    return Pool(n)


def cmd_maps(args):
    seeds = list(range(args.seed0, args.seed0 + args.seeds))
    jobs = []
    for ai, path in enumerate(args.agents):
        src = C.read(path)
        for k, _ in MAPS:
            s = with_land(src, k)
            for sd in seeds:
                jobs.append(((ai, k, sd), s, args.opponent, sd))
    with _pool(args.workers) as p:
        res = p.map(_play, jobs, chunksize=1)
    table = {}
    for (ai, k, sd), r in res:
        table.setdefault((ai, k), []).append((r["rewards"][0] or 0, r["rewards"][1] or 0, r["statuses"][0]))
    print(f"\nmean money over {len(seeds)} seeds, opponent = {args.opponent}  (min in brackets)")
    print(f"{'agent':<34}" + "".join(f"{name:>20}" for _, name in MAPS))
    for ai, path in enumerate(args.agents):
        row = f"{os.path.relpath(path, ROOT)[:33]:<34}"
        for k, _ in MAPS:
            v = [x[0] for x in table[(ai, k)]]
            bad = sum(1 for x in table[(ai, k)] if x[2] != "DONE")
            row += f"{statistics.mean(v):>11,.0f} ({min(v):>6,.0f})" + ("!" if bad else "")
        print(row)


def cmd_duel(args):
    a, b = C.read(args.a), C.read(args.b)
    jobs = []
    for sd in range(args.seed0, args.seed0 + args.seeds):
        jobs.append(((sd, 0), a, b, sd))
        jobs.append(((sd, 1), b, a, sd))
    with _pool(args.workers) as p:
        res = p.map(_play, jobs, chunksize=1)
    score, ma, mb = 0.0, [], []
    for (sd, seat), r in res:
        me, op = r["rewards"][seat] or 0, r["rewards"][1 - seat] or 0
        score += 1.0 if me > op else 0.5 if me == op else 0.0
        ma.append(me)
        mb.append(op)
    n = len(res)
    print(f"{os.path.relpath(args.a, ROOT)} vs {os.path.relpath(args.b, ROOT)}: "
          f"score {score}/{n} ({100 * score / n:.0f}%), money {statistics.mean(ma):,.0f} vs {statistics.mean(mb):,.0f}")


def cmd_ghost(args):
    from kaggle_environments import make
    from kaggle_environments.agent import get_last_callable

    with open(args.episode, encoding="utf-8") as f:
        ep = json.load(f)
    names = ep.get("info", {}).get("TeamNames") or ["p0", "p1"]
    seed = ep.get("info", {}).get("seed")
    rewards = ep.get("rewards")
    me = args.seat if args.seat is not None else 0
    opp = 1 - me
    print(f"episode {ep.get('id')} seed {seed}: {names[0]} {rewards[0]:,.0f} vs {names[1]} {rewards[1]:,.0f}")
    print(f"ghost = {names[opp]} (recorded moves); you play seat {me}")
    for path in args.agents:
        agent = get_last_callable(C.read(path), path=path)
        ghost = _ghost_agent(args.episode, opp)
        env = make("kaggriculture", configuration={"seed": seed})
        env.run([agent, ghost] if me == 0 else [ghost, agent])
        last = env.steps[-1]
        a, g = last[me].reward or 0, last[opp].reward or 0
        print(f"  {os.path.relpath(path, ROOT):<34} {a:>10,.0f}  vs ghost {g:>10,.0f}  "
              f"{'WIN' if a > g else 'loss'}  ({last[me].status})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("maps", help="every agent on 5x5 / 5x10 / 5x10+5x5 / 10x10")
    m.add_argument("--agents", nargs="+", required=True)
    m.add_argument("--opponent", default="starter", help="starter (default) or a main.py path")
    m.add_argument("--seeds", type=int, default=4)
    m.add_argument("--seed0", type=int, default=1)
    m.add_argument("--workers", type=int, default=os.cpu_count() or 2)
    m.set_defaults(fn=cmd_maps)
    d = sub.add_parser("duel", help="head-to-head, both seats")
    d.add_argument("a")
    d.add_argument("b")
    d.add_argument("--seeds", type=int, default=10)
    d.add_argument("--seed0", type=int, default=100)
    d.add_argument("--workers", type=int, default=os.cpu_count() or 2)
    d.set_defaults(fn=cmd_duel)
    g = sub.add_parser("ghost", help="replay the opponent of a Kaggle episode JSON")
    g.add_argument("episode")
    g.add_argument("--agents", nargs="+", required=True)
    g.add_argument("--seat", type=int, default=None, help="your seat in the episode (default 0)")
    g.set_defaults(fn=cmd_ghost)
    args = ap.parse_args()
    if getattr(args, "opponent", None) and args.opponent not in C.BUILTIN:
        args.opponent = C.read(args.opponent)
    args.fn(args)


if __name__ == "__main__":
    main()
