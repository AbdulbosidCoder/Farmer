"""Self-play evolutionary trainer for Kaggriculture.

Every generation:
  1. each candidate (a PARAMS vector for the agent file) plays full 720-turn games
     on the official kaggle_environments engine against
       - other members of the population (self-play),
       - champions of earlier generations (hall of fame, prevents forgetting),
       - benchmarks: agents/v8/main.py (if present) and the built-in "starter";
  2. fitness = win rate + margin bonus;
  3. the champion is saved to avlod/avlod_NNN/ as a ready-to-submit main.py;
  4. the champion is promoted to avlod/best/ only if it beats the current best
     head-to-head (gate match);
  5. the next population = elites + tournament-selected, crossed-over, mutated children.

Usage:
    python -m trainer.evolve --generations 30 --pop 12 --workers 4
    python -m trainer.evolve --resume              # continue from the last avlod
    python -m trainer.evolve --agent agents/v8/main.py   # evolve v8's own PARAMS
"""
import argparse
import csv
import glob
import math
import os
import random
import sys
import time
from multiprocessing import Pool

from trainer import common as C


# ------------------------------------------------------------------ genome
def auto_bounds(params):
    b = {}
    for k, v in params.items():
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            continue
        lo, hi = (0.0, max(1.0, 2.0 * abs(v))) if v >= 0 else (2.0 * v, 0.0)
        b[k] = (lo, hi)
    return b


def mutate(params, bounds, rng, rate, sigma):
    child = dict(params)
    for k, (lo, hi) in bounds.items():
        if rng.random() < rate:
            v = float(child[k]) + rng.gauss(0.0, sigma * (hi - lo))
            child[k] = min(hi, max(lo, v))
    return child


def crossover(a, b, bounds, rng):
    child = dict(a)
    for k in bounds:
        r = rng.random()
        if r < 0.4:
            child[k] = b[k]
        elif r < 0.6:  # blend
            child[k] = 0.5 * (float(a[k]) + float(b[k]))
    return child


def tournament(pop, rng, k=3):
    group = rng.sample(pop, min(k, len(pop)))
    return max(group, key=lambda c: c["fitness"])


# ------------------------------------------------------------------ scoring
def game_score(me, opp, status):
    if status != "DONE" or me is None:
        return 0.0, -1.0
    opp = opp if opp is not None else 0.0
    win = 1.0 if me > opp else (0.5 if me == opp else 0.0)
    margin = (me - opp) / max(abs(me), abs(opp), 1.0)
    return win, margin


def list_generations():
    dirs = sorted(glob.glob(os.path.join(C.AVLOD_DIR, "avlod_[0-9]*")))
    return [d for d in dirs if os.path.exists(os.path.join(d, "main.py"))]


# ------------------------------------------------------------------ main loop
def run(args):
    rng = random.Random(args.seed)
    agent_path = os.path.abspath(args.agent)
    template = C.read(agent_path)
    seed_params = C.extract_params(template)
    if not seed_params:
        sys.exit(f"{agent_path}: no PARAMS dict literal found - cannot evolve this agent")
    bounds = C.extract_bounds(template) or auto_bounds(seed_params)
    bounds = {k: v for k, v in bounds.items() if k in seed_params}

    os.makedirs(C.AVLOD_DIR, exist_ok=True)
    state_path = os.path.join(C.AVLOD_DIR, "population.json")
    gens = list_generations()
    start_gen = 1
    pop = None
    if args.resume and os.path.exists(state_path):
        import json

        with open(state_path) as f:
            st = json.load(f)
        pop = [{"params": {**seed_params, **p["params"]}, "fitness": p.get("fitness", 0.0)} for p in st["population"]]
        start_gen = st["generation"] + 1
        print(f"resume from generation {st['generation']} ({len(pop)} candidates)")
    if pop is None:
        if gens and not args.fresh:
            sys.exit("avlod/ already has generations: use --resume to continue or --fresh to start over")
        pop = [{"params": dict(seed_params), "fitness": 0.0}]
        while len(pop) < args.pop:
            pop.append({"params": mutate(seed_params, bounds, rng, 0.5, 0.15), "fitness": 0.0})

    rng = random.Random(args.seed * 1000 + start_gen)
    v8_src = C.read(C.V8_AGENT) if os.path.exists(C.V8_AGENT) and not args.no_v8 else None
    if v8_src:
        print("benchmark: agents/v8/main.py found - it is in every generation's opponent pool")
    else:
        print("benchmark: agents/v8/main.py not found - training vs self-play + hall of fame + starter")

    hist_path = os.path.join(C.AVLOD_DIR, "history.csv")
    pool = Pool(args.workers)
    try:
        for gen in range(start_gen, start_gen + args.generations):
            t0 = time.time()
            for c in pop:
                c["src"] = C.render(template, c["params"])
                c["games"] = []

            hof = [C.read(os.path.join(d, "main.py")) for d in list_generations()[-args.hof_size:]]
            best_path = os.path.join(C.AVLOD_DIR, "best", "main.py")

            jobs = []
            n = len(pop)
            for i in range(n):
                opps = [("self", j) for j in rng.sample([j for j in range(n) if j != i], min(args.games_self, n - 1))]
                opps += [("hof", h) for h in (rng.sample(range(len(hof)), min(args.games_hof, len(hof))) if hof else [])]
                if v8_src:
                    opps += [("v8", None)] * args.games_v8
                opps += [("starter", None)] * args.games_starter
                for g, (kind, j) in enumerate(opps):
                    seed = rng.randrange(1, 2**31)
                    if kind == "self":
                        osrc = pop[j]["src"]
                    elif kind == "hof":
                        osrc = hof[j]
                    elif kind == "v8":
                        osrc = v8_src
                    else:
                        osrc = "starter"
                    seat = g % 2  # alternate seats: the engine is symmetric but be safe
                    pair = (pop[i]["src"], osrc) if seat == 0 else (osrc, pop[i]["src"])
                    jobs.append(((i, kind, j, seat), pair[0], pair[1], seed))

            results = pool.map(C.play_job, jobs, chunksize=1)
            vs = {"v8": [], "starter": [], "hof": []}
            for (i, kind, j, seat), r in results:
                me, opp = r["rewards"][seat], r["rewards"][1 - seat]
                w, m = game_score(me, opp, r["statuses"][seat])
                pop[i]["games"].append((kind, w, m, me or 0.0))
                # self-play games also count (mirrored) for the opponent candidate
                if kind == "self":
                    w2, m2 = game_score(opp, me, r["statuses"][1 - seat])
                    pop[j]["games"].append(("self", w2, m2, opp or 0.0))
                if kind in vs:
                    vs[kind].append(w)

            for c in pop:
                g = c["games"]
                wr = sum(x[1] for x in g) / len(g)
                mg = sum(x[2] for x in g) / len(g)
                money = sum(x[3] for x in g) / len(g)
                c["fitness"] = wr + 0.5 * mg + 0.05 * money / 50000.0
                c["winrate"], c["margin"], c["money"] = wr, mg, money
                v8g = [x[1] for x in g if x[0] == "v8"]
                c["v8_winrate"] = sum(v8g) / len(v8g) if v8g else None
            pop.sort(key=lambda c: -c["fitness"])
            champ = pop[0]

            # ---- save generation
            gdir = os.path.join(C.AVLOD_DIR, f"avlod_{gen:03d}")
            os.makedirs(gdir, exist_ok=True)
            with open(os.path.join(gdir, "main.py"), "w", encoding="utf-8") as f:
                f.write(champ["src"])
            C.save_json(os.path.join(gdir, "params.json"), champ["params"])
            stats = {
                "generation": gen,
                "agent_template": os.path.relpath(agent_path, C.ROOT),
                "fitness": champ["fitness"],
                "winrate": champ["winrate"],
                "margin": champ["margin"],
                "avg_money": champ["money"],
                "v8_winrate": champ["v8_winrate"],
                "pop_winrate_vs_v8": (sum(vs["v8"]) / len(vs["v8"])) if vs["v8"] else None,
                "pop_winrate_vs_starter": (sum(vs["starter"]) / len(vs["starter"])) if vs["starter"] else None,
                "pop_winrate_vs_hof": (sum(vs["hof"]) / len(vs["hof"])) if vs["hof"] else None,
                "games": len(results),
                "errors": sum(1 for _, r in results if "ERROR" in r["statuses"]),
                "seconds": round(time.time() - t0, 1),
                "population": [
                    {"fitness": round(c["fitness"], 4), "winrate": round(c["winrate"], 3), "money": round(c["money"])}
                    for c in pop
                ],
            }

            # ---- gate: promote to avlod/best only if it beats the current best
            promoted = False
            if not os.path.exists(best_path):
                promoted = True
            else:
                best_src = C.read(best_path)
                gjobs = []
                for g in range(args.gate_games):
                    s = rng.randrange(1, 2**31)
                    pair = (champ["src"], best_src) if g % 2 == 0 else (best_src, champ["src"])
                    gjobs.append(((g % 2,), pair[0], pair[1], s))
                gres = pool.map(C.play_job, gjobs, chunksize=1)
                ws = [game_score(r["rewards"][k[0]], r["rewards"][1 - k[0]], r["statuses"][k[0]])[0] for k, r in gres]
                stats["gate_winrate_vs_best"] = sum(ws) / len(ws)
                promoted = stats["gate_winrate_vs_best"] > 0.5
            stats["promoted_to_best"] = promoted
            if promoted:
                bdir = os.path.join(C.AVLOD_DIR, "best")
                os.makedirs(bdir, exist_ok=True)
                with open(os.path.join(bdir, "main.py"), "w", encoding="utf-8") as f:
                    f.write(champ["src"])
                C.save_json(os.path.join(bdir, "params.json"), champ["params"])
                C.save_json(os.path.join(bdir, "info.json"), {"from_generation": gen, **{k: stats[k] for k in ("fitness", "winrate", "avg_money", "v8_winrate")}})
            C.save_json(os.path.join(gdir, "stats.json"), stats)

            new_file = not os.path.exists(hist_path)
            with open(hist_path, "a", newline="") as f:
                w = csv.writer(f)
                if new_file:
                    w.writerow(["generation", "fitness", "winrate", "avg_money", "v8_winrate", "pop_vs_starter", "pop_vs_hof", "gate_vs_best", "promoted", "seconds"])
                w.writerow([gen, round(champ["fitness"], 4), round(champ["winrate"], 3), round(champ["money"]),
                            stats["v8_winrate"], stats["pop_winrate_vs_starter"], stats["pop_winrate_vs_hof"],
                            stats.get("gate_winrate_vs_best"), promoted, stats["seconds"]])

            print(f"[avlod {gen:03d}] fitness={champ['fitness']:.3f} winrate={champ['winrate']:.2f} "
                  f"money={champ['money']:.0f} v8={champ['v8_winrate']} best={'NEW' if promoted else 'kept'} "
                  f"({stats['seconds']}s, {len(results)} games)", flush=True)

            # ---- next population
            sigma = args.sigma * (0.5 + 0.5 * math.exp(-gen / 30.0))
            nxt = [{"params": dict(c["params"]), "fitness": c["fitness"]} for c in pop[: args.elites]]
            while len(nxt) < args.pop:
                a = tournament(pop, rng)
                if rng.random() < args.cx:
                    b = tournament(pop, rng)
                    child = crossover(a["params"], b["params"], bounds, rng)
                else:
                    child = dict(a["params"])
                nxt.append({"params": mutate(child, bounds, rng, args.mut_rate, sigma), "fitness": 0.0})
            C.save_json(state_path, {"generation": gen, "population": [{"params": c["params"], "fitness": c["fitness"]} for c in nxt]})
            pop = nxt
    finally:
        pool.close()
        pool.join()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agent", default=C.BASE_AGENT, help="agent template with a PARAMS dict (default: agents/base/main.py)")
    ap.add_argument("--generations", type=int, default=10)
    ap.add_argument("--pop", type=int, default=10)
    ap.add_argument("--elites", type=int, default=3)
    ap.add_argument("--games-self", type=int, default=4)
    ap.add_argument("--games-hof", type=int, default=2)
    ap.add_argument("--games-v8", type=int, default=2)
    ap.add_argument("--games-starter", type=int, default=0)
    ap.add_argument("--hof-size", type=int, default=5)
    ap.add_argument("--gate-games", type=int, default=6)
    ap.add_argument("--mut-rate", type=float, default=0.25)
    ap.add_argument("--sigma", type=float, default=0.12)
    ap.add_argument("--cx", type=float, default=0.5)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2)))
    ap.add_argument("--seed", type=int, default=12345)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--fresh", action="store_true", help="allow starting a new run even if avlod/ has generations")
    ap.add_argument("--no-v8", action="store_true")
    run(ap.parse_args())


if __name__ == "__main__":
    main()
