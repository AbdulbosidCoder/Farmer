"""Kaggriculture parametric agent.

Single-file, dependency-free agent (Kaggle submission format: `main.py` with the
`agent` function as the LAST callable in the file).

All strategic knobs live in PARAMS. The self-play trainer (`trainer/evolve.py`)
rewrites the block between the PARAMS markers for every generation it saves
under `avlod/`.
"""
import math
import os

# === PARAMS BEGIN ===
PARAMS = {'w_WHEAT': 0.3796,
 'w_CARROT': 0.1179,
 'w_TOMATO': 0.1672,
 'w_STRAWBERRY': 0.3018,
 'w_MELON': 0.0,
 'w_GOOSE': 0.3788,
 'w_COW': 0.1,
 'w_SHEEP': 0.1434,
 'max_GOOSE': 20.0,
 'max_COW': 5.6581,
 'max_SHEEP': 5.0,
 'last_day_GOOSE': 19.4718,
 'last_day_COW': 13.3253,
 'last_day_SHEEP': 10.1373,
 'hold_WHEAT': 0.6,
 'hold_CARROT': 0.5,
 'hold_TOMATO': 0.8986,
 'hold_STRAWBERRY': 0.5,
 'hold_MELON': 0.5,
 'hold_EGG': 0.5,
 'hold_MILK': 0.651,
 'hold_WOOL': 0.5,
 'hold_FERTILIZER': 0.5,
 'panic_day': 27.0,
 'hands_per_job': 0.4363,
 'max_hands': 6.0,
 'land1_day': 3.0,
 'land2_day': 7.0,
 'land3_day': 12.0,
 'land_last_day': 19.9038,
 'land_reserve': 0.3,
 'cash_reserve': 150.0,
 'fert_use': 0.4502,
 'fert_keep': 4.0,
 'carry_limit': 20.0,
 'wheat_days': 2.0,
 'melon_age': 10.4409,
 'plant_margin': 0.0,
 'dist_weight': 2.0309,
 'urgency': 62.9952,
 'seed_batch': 5.4878}
# === PARAMS END ===

# Search space used by trainer/evolve.py (min, max) for every PARAMS entry.
PARAM_BOUNDS = {
    "w_WHEAT": (0.0, 1.0), "w_CARROT": (0.0, 1.0), "w_TOMATO": (0.0, 1.0), "w_STRAWBERRY": (0.0, 1.0),
    "w_MELON": (0.0, 1.0), "w_GOOSE": (0.0, 1.0), "w_COW": (0.0, 1.0), "w_SHEEP": (0.0, 1.0),
    "max_GOOSE": (0.0, 40.0), "max_COW": (0.0, 20.0), "max_SHEEP": (0.0, 20.0),
    "last_day_GOOSE": (0.0, 28.0), "last_day_COW": (0.0, 28.0), "last_day_SHEEP": (0.0, 28.0),
    "hold_WHEAT": (0.0, 1.2), "hold_CARROT": (0.0, 1.2), "hold_TOMATO": (0.0, 1.2),
    "hold_STRAWBERRY": (0.0, 1.2), "hold_MELON": (0.0, 1.2), "hold_EGG": (0.0, 1.2),
    "hold_MILK": (0.0, 1.2), "hold_WOOL": (0.0, 1.2), "hold_FERTILIZER": (0.0, 1.2),
    "panic_day": (20.0, 29.0),
    "hands_per_job": (0.05, 1.0), "max_hands": (0.0, 14.0),
    "land1_day": (0.0, 20.0), "land2_day": (0.0, 24.0), "land3_day": (0.0, 26.0), "land_last_day": (0.0, 26.0),
    "land_reserve": (0.0, 2.0), "cash_reserve": (0.0, 1500.0),
    "fert_use": (0.0, 2.0), "fert_keep": (0.0, 20.0),
    "carry_limit": (3.0, 60.0), "wheat_days": (1.0, 4.0), "melon_age": (10.0, 12.0),
    "plant_margin": (0.0, 3.0), "dist_weight": (0.2, 3.0), "urgency": (0.0, 200.0), "seed_batch": (1.0, 25.0),
}

CROPS = {
    "WHEAT": {"seed": 10, "first": 2, "maxd": 4, "interval": 0, "cap": 6, "ongoing": False, "base": 25},
    "CARROT": {"seed": 20, "first": 2, "maxd": 3, "interval": 0, "cap": 4, "ongoing": False, "base": 35},
    "TOMATO": {"seed": 50, "first": 8, "maxd": 8, "interval": 1, "cap": 4, "ongoing": True, "base": 60},
    "STRAWBERRY": {"seed": 100, "first": 10, "maxd": 10, "interval": 2, "cap": 4, "ongoing": True, "base": 120},
    "MELON": {"seed": 80, "first": 10, "maxd": 12, "interval": 0, "cap": 6, "ongoing": False, "base": 250},
}
ANIMALS = {
    "GOOSE": {"cost": 300, "struct": "COOP", "product": "EGG"},
    "COW": {"cost": 400, "struct": "PASTURE", "product": "MILK"},
    "SHEEP": {"cost": 500, "struct": "PASTURE", "product": "WOOL"},
}
MARKET = {
    "WHEAT": (25, 400, "sqrt", 0.80, "log", 0.20),
    "CARROT": (35, 450, "hinge", 1.00, "sqrt", 0.70),
    "TOMATO": (60, 200, "hinge", 0.40, "sqrt", 0.60),
    "STRAWBERRY": (120, 100, "sqrt", 0.70, "linear", 1.60),
    "MELON": (250, 300, "log", 0.20, "sq", 3.60),
    "EGG": (50, 332, "hinge", 0.40, "log", 0.20),
    "MILK": (160, 122, "sqrt", 0.60, "linear", 1.60),
    "WOOL": (200, 105, "log", 0.20, "sq", 3.20),
    "FERTILIZER": (100, 200, "linear", 0.40, "linear", 0.40),
}
I0 = 10000
TYPES = ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "GOOSE", "COW", "SHEEP"]
LAND_PRICES = [1000, 2000, 4000]
MOVES = {"NORTH": (0, -1), "SOUTH": (0, 1), "EAST": (1, 0), "WEST": (-1, 0)}

_MEM = {}


def _shape(func, x, T):
    x = max(0.0, x)
    if func == "linear":
        return x
    if func == "sq":
        return x * x
    if func == "sqrt":
        return math.sqrt(x)
    if func == "log":
        return math.log(1.0 + x)
    if func == "hinge":
        u = x / T
        return u + 8.0 * max(0.0, u - 1.0) ** 2
    return x


def _price(item, inv):
    base, T, bf, bt, af, at = MARKET[item]
    if inv < I0:
        p = base + bt * base / _shape(bf, T, T) * _shape(bf, I0 - inv, T)
    else:
        p = base - at * base / _shape(af, T, T) * _shape(af, inv - I0, T)
    return max(1, int(round(p)))


def _g(d, k, default=None):
    try:
        v = d.get(k, default)
    except AttributeError:
        v = getattr(d, k, default)
    return default if v is None else v


def _harvest_age(crop):
    c = CROPS[crop]
    if crop == "MELON":
        return int(min(c["maxd"], max(c["first"], round(PARAMS["melon_age"]))))
    return c["maxd"]


def _crop_feasible(crop, day, last_day):
    c = CROPS[crop]
    margin = int(round(PARAMS["plant_margin"]))
    if c["ongoing"]:
        # at least two scheduled productions before the end
        need = c["first"] + c["interval"]
        return day + need + margin <= last_day
    return day + _harvest_age(crop) + margin <= last_day


def _shed_tiles(n):
    h = n // 2
    return [(h - 1, h - 1), (h, h - 1), (h - 1, h), (h, h)]


def _step_toward(pos, tgt):
    x, y = pos
    tx, ty = tgt
    if tx > x:
        return "EAST"
    if tx < x:
        return "WEST"
    if ty > y:
        return "SOUTH"
    if ty < y:
        return "NORTH"
    return "PASS"


def _inv_count(inv, items=None):
    if items is None:
        return sum(v for v in inv.values() if v > 0)
    return sum(inv.get(i, 0) for i in items)


SELLABLE = ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL", "FERTILIZER"]
PRODUCE = ["CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL"]


def _plan(obs, cfg_steps=720, tpd=24):
    player = _g(obs, "player", 0)
    farms = _g(obs, "farms", [])
    me = farms[player]
    priv = _g(obs, "private", {}) or {}
    shed = dict(_g(priv, "shed", {}) or {})
    seeds = dict(_g(priv, "seeds", {}) or {})
    invs = [dict(i or {}) for i in (_g(priv, "inventories", [{}]) or [{}])]
    market = _g(obs, "market", {}) or {}
    minv = dict(_g(market, "inventory", {}) or {})
    day = int(_g(obs, "day", 0))
    hour = int(_g(obs, "hour", 0))
    last_day = cfg_steps // tpd - 1
    tiles = me["tiles"]
    n = len(tiles)
    money = float(me["money"])
    units = [tuple(me["farmer"])] + [tuple(h) for h in me["hands"]]
    while len(invs) < len(units):
        invs.append({})
    shed_tiles = _shed_tiles(n)
    step = day * tpd + hour
    final_step = cfg_steps - 2  # last step whose actions are processed

    mem = _MEM.setdefault(player, {"plan": {}, "target": {}})
    plan = mem["plan"]

    # ---------------------------------------------------------- census
    count = {t: 0 for t in TYPES}
    animals = []
    empty_structs = []
    for y in range(n):
        for x in range(n):
            t = tiles[y][x]
            if isinstance(t, dict):
                k = t.get("kind")
                if k == "PLANT":
                    count[t["crop"]] += 1
                    plan.pop((x, y), None)
                elif t.get("animal"):
                    count[t["animal"]] += 1
                    animals.append((x, y))
                    plan.pop((x, y), None)
                elif k in ("COOP", "PASTURE"):
                    empty_structs.append((x, y))
            elif t is None:
                pass
    for (x, y), role in list(plan.items()):
        t = tiles[y][x]
        if t == "LOCKED" or (isinstance(t, dict) and t.get("kind") == "PLANT"):
            plan.pop((x, y), None)
            continue
        count[role] = count.get(role, 0) + 1

    unlocked = sum(1 for row in tiles for t in row if t != "LOCKED")
    wsum = sum(max(0.0, PARAMS["w_" + t]) for t in TYPES) or 1.0

    def choose_role(x, y):
        best, best_def = None, -1e9
        for t in TYPES:
            w = max(0.0, PARAMS["w_" + t])
            if w <= 0:
                continue
            if t in ANIMALS:
                if day > PARAMS["last_day_" + t] or count[t] >= PARAMS["max_" + t]:
                    continue
            elif not _crop_feasible(t, day, last_day):
                continue
            deficit = w / wsum * unlocked - count[t]
            if deficit > best_def:
                best, best_def = t, deficit
        if best is None:
            for t in ("CARROT", "WHEAT"):
                if _crop_feasible(t, day, last_day):
                    return t
        return best

    # assign roles to empty tiles / empty structures
    for y in range(n):
        for x in range(n):
            t = tiles[y][x]
            if t is None and (x, y) not in plan:
                r = choose_role(x, y)
                if r:
                    plan[(x, y)] = r
                    count[r] += 1
            elif t is None and (x, y) in plan:
                r = plan[(x, y)]
                ok = (day <= PARAMS["last_day_" + r]) if r in ANIMALS else _crop_feasible(r, day, last_day)
                if not ok:
                    count[r] -= 1
                    plan.pop((x, y))
                    r2 = choose_role(x, y)
                    if r2:
                        plan[(x, y)] = r2
                        count[r2] += 1
    for (x, y) in empty_structs:
        t = tiles[y][x]
        want = [a for a in ANIMALS if ANIMALS[a]["struct"] == t["kind"]]
        cur = plan.get((x, y))
        if cur not in want:
            cand = [a for a in want if day <= PARAMS["last_day_" + a] and count[a] < PARAMS["max_" + a] + 1]
            if cand:
                cand.sort(key=lambda a: -(PARAMS["w_" + a] / wsum * unlocked - count[a]))
                plan[(x, y)] = cand[0]
                count[cand[0]] += 1
            else:
                plan.pop((x, y), None)
        elif day > PARAMS["last_day_" + cur]:
            plan.pop((x, y), None)

    jobs = sum(1 for row in tiles for t in row if isinstance(t, dict)) + len(plan)
    exp_units = 1 + int(min(PARAMS["max_hands"], round(jobs * PARAMS["hands_per_job"])))
    return dict(exp_units=exp_units, player=player, me=me, shed=shed, seeds=seeds, invs=invs, minv=minv, day=day,
                hour=hour, last_day=last_day, tiles=tiles, n=n, money=money, units=units,
                shed_tiles=shed_tiles, step=step, final_step=final_step, plan=plan,
                animals=animals, empty_structs=empty_structs, mem=mem, tpd=tpd, count=count)


def _tile_actions(S, x, y, inv, seeds_left):
    """Candidate (priority, op) actions a unit carrying `inv` could do on tile (x, y)."""
    t = S["tiles"][y][x]
    urg = PARAMS["urgency"] * S["hour"] / S["tpd"]
    day, last_day = S["day"], S["last_day"]
    final = day == last_day
    plan = S["plan"]
    out = []
    if t == "LOCKED":
        return out
    if t is None:
        role = plan.get((x, y))
        if final or role is None:
            return out
        if role in CROPS:
            if seeds_left.get(role, 0) > 0:
                out.append((45, ["PLANT", role]))
        else:
            out.append((35, ["BUILD_COOP"] if ANIMALS[role]["struct"] == "COOP" else ["BUILD_PASTURE"]))
        return out
    kind = t.get("kind")
    if kind == "WEED":
        if not final and (x, y) in plan or not final:
            out.append((15, ["DIG"]))
        return out
    if kind == "PLANT":
        crop = t["crop"]
        c = CROPS[crop]
        age = day - t["planted_day"]
        yu = t.get("yield_units", 0)
        watered = t.get("watered_today")
        if c["ongoing"]:
            if not watered and not final:
                out.append((40 + urg * (1 + t.get("consecutive_unwatered", 0)), ["WATER"]))
            if yu > 0 and age >= c["first"]:
                out.append((50 if (yu >= 2 or final or yu >= c["cap"] - 1) else 20, ["HARVEST"]))
            if (inv.get("FERTILIZER", 0) > 0 and PARAMS["fert_use"] > 0.5 and not final
                    and t.get("fertilized_until_day", -1) < day and age >= c["first"] - 1
                    and t.get("max_lifespan_step", -1) < 0):
                out.append((45, ["FERTILIZE"]))
        else:
            ha = _harvest_age(crop)
            window = (c["maxd"] + 1) // 2
            ready = age >= ha or (final and age >= c["first"])
            decaying = t.get("max_lifespan_step", -1) >= 0 and S["step"] >= t["max_lifespan_step"] - 2
            if not watered and (not ready or window <= age <= c["maxd"]):
                out.append((40 + urg * (1 + t.get("consecutive_unwatered", 0)), ["WATER"]))
            if ready or (decaying and age >= c["first"]):
                if watered or not (window <= age <= c["maxd"]) or decaying:
                    out.append((70 if decaying else 55, ["HARVEST"]))
            if (inv.get("FERTILIZER", 0) > 0 and PARAMS["fert_use"] > 1.2 and not final
                    and t.get("fertilized_until_day", -1) < day and window <= age < ha):
                out.append((45, ["FERTILIZE"]))
        return out
    if t.get("animal"):
        if not t.get("fed_today") and inv.get("WHEAT", 0) > 0 and not final:
            out.append((45 + urg * (1 + t.get("consecutive_unfed", 0)), ["FEED"]))
        if not t.get("cared_today") and not final:
            out.append((35, ["CARE"]))
        if t.get("yield_units", 0) > 0:
            out.append((50, ["HARVEST"]))
        if t.get("fertilizer_available"):
            out.append((30, ["COLLECT_FERTILIZER"]))
        return out
    if kind in ("COOP", "PASTURE"):
        role = S["plan"].get((x, y))
        carried = [a for a in ANIMALS if ANIMALS[a]["struct"] == kind and inv.get(a, 0) > 0]
        if carried:
            out.append((65, ["PLACE", carried[0], 1]))
        elif role is None and not final:
            out.append((10, ["DIG"]))
    return out


def _market(S, orders_budget=10):
    day, hour, money = S["day"], S["hour"], S["money"]
    shed, seeds, plan, invs = S["shed"], S["seeds"], S["plan"], S["invs"]
    minv = S["minv"]
    orders = []
    spend = 0.0
    reserve = PARAMS["cash_reserve"]
    final = day == S["last_day"]
    n_animals = len(S["animals"])

    # ---- sell
    wheat_reserve = 0 if final else int(math.ceil(n_animals * PARAMS["wheat_days"])) - _inv_count_all(invs, "WHEAT")
    fert_reserve = 0 if final else int(PARAMS["fert_keep"]) if PARAMS["fert_use"] > 0.5 else 0
    shed_total = sum(v for v in shed.values() if v > 0)
    pressure = shed_total > 70
    income = 0.0
    for item in SELLABLE:
        have = shed.get(item, 0)
        if item == "WHEAT":
            have -= max(0, wheat_reserve)
        if item == "FERTILIZER":
            have -= fert_reserve
        if have <= 0:
            continue
        base = MARKET[item][0]
        if day >= PARAMS["panic_day"] or final:
            thr = 1
        else:
            thr = PARAMS["hold_" + item] * base * (0.5 if pressure else 1.0)
        inv = minv.get(item, I0)
        k = 0
        while k < have:
            p = _price(item, inv)
            if p < thr:
                break
            income += p
            if p > 1:
                inv += 1
            k += 1
        if k > 0:
            orders.append(["SELL", item, k])
    avail = money + income - reserve

    # ---- wheat for feed (animals die without it: buy first)
    if n_animals and not final:
        need_w = int(math.ceil(n_animals * PARAMS["wheat_days"])) - shed.get("WHEAT", 0) - _inv_count_all(invs, "WHEAT")
        if need_w > 0:
            wp = _price("WHEAT", minv.get("WHEAT", I0) - need_w) + 1
            k = min(need_w, int(max(0, money + income - spend) // wp))
            if k > 0:
                orders.append(["BUY_PRODUCT", "WHEAT", k])
                spend += k * wp

    # ---- hire hands (only at start of day)
    if hour == 0:
        jobs = sum(1 for row in S["tiles"] for t in row if isinstance(t, dict)) + len(plan)
        want = int(min(PARAMS["max_hands"], round(jobs * PARAMS["hands_per_job"])))
        hires = S["me"].get("hires_today", 0)
        a, b = 1, 1
        for _ in range(hires):
            a, b = b, a + b
        while hires < want and len(orders) < orders_budget and a <= money + income - spend:
            orders.append(["HIRE"])
            spend += a
            hires += 1
            a, b = b, a + b

    # ---- land
    nq = len(S["me"]["unlocked_quadrants"]) - 1
    if nq < 3 and day <= PARAMS["land_last_day"] and day >= PARAMS["land%d_day" % (nq + 1)]:
        cost = LAND_PRICES[nq]
        if avail - spend >= cost * (1 + PARAMS["land_reserve"]):
            orders.append(["BUY_LAND"])
            spend += cost

    # ---- animals (keep money for a few days of their feed)
    want_a = {}
    for (x, y) in S["empty_structs"]:
        role = plan.get((x, y))
        if role in ANIMALS:
            want_a[role] = want_a.get(role, 0) + 1
    for a, k in want_a.items():
        k -= shed.get(a, 0) + _inv_count_all(invs, a)
        cost = ANIMALS[a]["cost"] + 30 * PARAMS["wheat_days"]
        k = min(k, int(max(0, avail - spend) // cost))
        if k > 0 and len(orders) < orders_budget:
            orders.append(["BUY_ANIMAL", a, k])
            spend += k * cost

    # ---- seeds
    need = {}
    for (x, y), role in plan.items():
        if role in CROPS and S["tiles"][y][x] is None:
            need[role] = need.get(role, 0) + 1
    for crop, k in sorted(need.items(), key=lambda kv: CROPS[kv[0]]["seed"]):
        k = min(k, int(PARAMS["seed_batch"])) - seeds.get(crop, 0)
        cost = CROPS[crop]["seed"]
        k = min(k, int(max(0, avail - spend) // cost))
        if k > 0 and len(orders) < orders_budget:
            orders.append(["BUY_SEED", crop, k])
            spend += k * cost
    return orders[:orders_budget]


def _inv_count_all(invs, item):
    return sum(i.get(item, 0) for i in invs)


def _units(S):
    units, invs, tiles, n = S["units"], S["invs"], S["tiles"], S["n"]
    shed = dict(S["shed"])
    seeds_left = dict(S["seeds"])
    day, hour, step = S["day"], S["hour"], S["step"]
    final = day == S["last_day"]
    mem = S["mem"]
    targets = mem["target"]
    dist_w = PARAMS["dist_weight"]
    carry_limit = PARAMS["carry_limit"]

    unfed = sum(1 for (x, y) in S["animals"] if not tiles[y][x].get("fed_today"))
    carried_wheat = _inv_count_all(invs, "WHEAT")
    to_place = {}
    for (x, y) in S["empty_structs"]:
        r = S["plan"].get((x, y))
        if r in ANIMALS:
            to_place[r] = to_place.get(r, 0) + 1
    fert_targets = 0
    if PARAMS["fert_use"] > 0.5:
        for row in tiles:
            for t in row:
                if isinstance(t, dict) and t.get("kind") == "PLANT" and CROPS[t["crop"]]["ongoing"]:
                    fert_targets += 1
    carried_fert = _inv_count_all(invs, "FERTILIZER")

    claimed = set()
    actions = []
    fetcher = -1
    cand = [(min(abs(p[0] - sx) + abs(p[1] - sy) for sx, sy in S["shed_tiles"]), i)
            for i, p in enumerate(units) if invs[i].get("WHEAT", 0) == 0]
    if cand:
        fetcher = min(cand)[1]
    for ui, pos in enumerate(units):
        inv = invs[ui]
        at_shed = pos in S["shed_tiles"]
        load = _inv_count(inv, PRODUCE + ["WHEAT"]) - inv.get("WHEAT", 0)
        act = None

        # ---- endgame: bring everything home and drop it
        steps_left = S["final_step"] - 1 - step
        dshed = min(abs(pos[0] - sx) + abs(pos[1] - sy) for sx, sy in S["shed_tiles"])
        if final and _inv_count(inv) > 0 and steps_left <= dshed + 1:
            if at_shed:
                act = ["DROP"]
            else:
                tgt = min(S["shed_tiles"], key=lambda s: abs(pos[0] - s[0]) + abs(pos[1] - s[1]))
                act = [_step_toward(pos, tgt)]
            actions.append(act)
            continue

        if at_shed:
            # drop produce
            prod = [i for i in PRODUCE if inv.get(i, 0) > 0]
            if prod and (load >= carry_limit * 0.3 or final):
                actions.append(["PLACE", prod[0], inv[prod[0]]])
                continue
            # pick up animals to place
            for a, k in to_place.items():
                if k > 0 and shed.get(a, 0) > 0 and inv.get(a, 0) == 0:
                    act = ["PICKUP", a, 1]
                    shed[a] -= 1
                    to_place[a] -= 1
                    break
            share = int(math.ceil(unfed / max(1, len(units), S["exp_units"]))) + 1
            if (act is None and unfed > carried_wheat and shed.get("WHEAT", 0) > 0 and not final
                    and inv.get("WHEAT", 0) < share):
                k = min(shed["WHEAT"], unfed - carried_wheat, share - inv.get("WHEAT", 0))
                act = ["PICKUP", "WHEAT", k]
                shed["WHEAT"] -= k
                carried_wheat += k
            if act is None and fert_targets > carried_fert and shed.get("FERTILIZER", 0) > 0 and not final:
                k = min(shed["FERTILIZER"], fert_targets - carried_fert, 6)
                act = ["PICKUP", "FERTILIZER", k]
                shed["FERTILIZER"] -= k
                carried_fert += k
            if act is not None:
                actions.append(act)
                continue

        # ---- choose a tile
        best, best_score, best_op = None, -1e9, None
        prev = targets.get(ui)
        for y in range(n):
            for x in range(n):
                if (x, y) in claimed:
                    continue
                acts = _tile_actions(S, x, y, inv, seeds_left)
                if not acts:
                    continue
                pr, op = max(acts, key=lambda a: a[0])
                d = abs(pos[0] - x) + abs(pos[1] - y)
                score = pr - dist_w * d * 5 + (15 if prev == (x, y) else 0)
                if score > best_score:
                    best, best_score, best_op = (x, y), score, op

        # go home to drop a heavy load, or to fetch wheat
        need_home = load >= carry_limit
        if (not need_home and unfed > carried_wheat and inv.get("WHEAT", 0) == 0
                and shed.get("WHEAT", 0) > 0 and ui == fetcher and S["hour"] >= 2):
            need_home = True
        if need_home and not at_shed:
            tgt = min(S["shed_tiles"], key=lambda s: abs(pos[0] - s[0]) + abs(pos[1] - s[1]))
            actions.append([_step_toward(pos, tgt)])
            targets.pop(ui, None)
            continue

        if best is None:
            actions.append(["PASS"])
            targets.pop(ui, None)
            continue
        claimed.add(best)
        targets[ui] = best
        if best == pos:
            if best_op[0] == "PLANT":
                seeds_left[best_op[1]] -= 1
            if best_op[0] == "FEED":
                carried_wheat -= 1
            actions.append(best_op)
        else:
            actions.append([_step_toward(pos, best)])
    return actions


def agent(obs, config=None):
    steps = int(_g(config, "episodeSteps", 720)) if config is not None else 720
    tpd = int(_g(config, "turnsPerDay", 24)) if config is not None else 24
    if int(_g(obs, "day", 0)) == 0 and int(_g(obs, "hour", 0)) == 0:
        _MEM.clear()
    try:
        S = _plan(obs, steps, tpd)
        unit_actions = _units(S)
        market = _market(S)
        return {"farmer": unit_actions[0], "hands": unit_actions[1:], "market": market}
    except Exception:
        if os.environ.get("KAGG_DEBUG"):
            raise
        return {"farmer": ["PASS"], "hands": [], "market": []}
