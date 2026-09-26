"""v8 = v5 + omborning 4 ta kirishidan foydalanish.

O'lchangan: ish hududini omborning o'zidan reytinglash (v7) ZARAR qildi —
hayvonlar omborga yaqin to'planib turishi muhimroq ekan. Shuning uchun v8 da
hudud tanlash v5 dagidek qoladi, faqat YURISH maqsadi o'zgaradi: har birlik
eng yaqin ombor kirishiga boradi, hammasi bitta nuqtaga emas.

v3 faqat bug'doy ekardi va hayvonlarga tegmasdi. v4 hammasini ishlatadi.

Muhim mexanika (manbadan tekshirilgan):
  * FEED bug'doyni BIRLIK INVENTARIDAN oladi, ombordan emas. Ya'ni oziqlantirish
    uchun birlik avval omborda WHEAT ni PICKUP qilishi kerak.
  * Ketma-ket 2 kun oziqlantirilmagan hayvon qochib ketadi (qaytmaydi).
    Shuning uchun FEED eng yuqori ustuvorlikda, sug'orish bilan birga.
  * GOOSE interval=1 — HAR KUNI ishlab chiqaradi. CARE + FEED bo'lsa kuniga 2 tuxum.
    $50 x 2 = $100/kun, g'oz narxi $300 -> ~3 kunda qoplanadi. Eng kuchli aktiv.
  * EGG narxi hajmga chidamli ('log'), shuning uchun tuxumni cheklovsiz sotsa bo'ladi.
  * STRAWBERRY/MILK/WOOL/MELON tez quladi -> narx bazadan pastga tushsa sotilmaydi.
  * Ombor sig'imi 100; oshgani kun oxirida yo'qoladi -> to'lib ketishiga yo'l qo'ymaslik.
"""

SHED_TILES = frozenset({(4, 4), (5, 4), (4, 5), (5, 5)})
# Ish hududi shu nuqta atrofidagi Manhattan rombi sifatida tanlanadi.
# DIQQAT: (5,5) va (4,5) qulflangan janubiy choraklarda yotadi — romb o'sha
# tomonga kesilib, ochiq yerda UCHBURCHAK qoladi. Sweep uchun indeks bilan.
ANCHORS = [(4, 4), (5, 4), (4, 5), (5, 5)]
DROP_ANCHOR = 3
DROP_TARGET = ANCHORS[DROP_ANCHOR]
SEASON_DAYS = 30
SHED_CAPACITY = 100

CROPS = {
    "WHEAT":      {"seed": 10, "first": 2, "max_day": 4, "ongoing": False},
    "CARROT":     {"seed": 20, "first": 2, "max_day": 3, "ongoing": False},
    "TOMATO":     {"seed": 50, "first": 8, "max_day": 8, "ongoing": True},
    "STRAWBERRY": {"seed": 100, "first": 10, "max_day": 10, "ongoing": True},
    "MELON":      {"seed": 80, "first": 10, "max_day": 12, "ongoing": False},
}
ANIMALS = {
    "GOOSE": {"cost": 300, "structure": "COOP",    "product": "EGG"},
    "COW":   {"cost": 400, "structure": "PASTURE", "product": "MILK"},
    "SHEEP": {"cost": 500, "structure": "PASTURE", "product": "WOOL"},
}
BASE_PRICE = {"WHEAT": 25, "CARROT": 35, "TOMATO": 60, "STRAWBERRY": 120,
              "MELON": 250, "EGG": 50, "MILK": 160, "WOOL": 200, "FERTILIZER": 100}
# Hajmga chidamli ('log' shakli) — cheklovsiz sotiladi
GLUT_PROOF = frozenset({"WHEAT", "EGG"})

# Shahar do'konlari va ular talab qiladigan mahsulotlar. Do'konlar TASODIFIY
# ochiladi (har 3 kunda, takrorlanishi mumkin) va obs["town"] da ko'rinadi.
# Agent ularga moslashmasa, talabsiz mahsulot ishlab chiqarib narxni polga
# tushiradi: o'lchangan misol — YARN_STORE ochilmagan seedda jun narxi $246
# o'rniga $1 bo'lgan va natija 79,316 dan 37,576 ga tushgan.
SHOPS = {
    "BAKERY":         ["EGG", "WHEAT"],
    "PIZZA_SHOP":     ["MILK", "TOMATO", "WHEAT"],
    "BRUNCH_SPOT":    ["EGG", "WHEAT", "STRAWBERRY"],
    "YARN_STORE":     ["WOOL"],
    "ICE_CREAM_SHOP": ["STRAWBERRY", "MILK", "WHEAT"],
    "PET_CAFE":       ["CARROT"],
    "SMOOTHIE_SHOP":  ["STRAWBERRY", "MILK"],
    "FARMERS_MARKET": ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY"],
}
TOWN_CENTER_INTERVAL = 24
SHOP_SELL_INTERVAL = 4
ADAPT_TO_SHOPS = True     # hayvonni ochilgan do'konlarga qarab tanlash

# Hayvonning kunlik chiqimi (FEED+CARE bajarilsa). Talab bilan solishtirish uchun.
ANIMAL_RATE = {"GOOSE": 2.0, "COW": 1.5, "SHEEP": 4.0 / 3.0}


def _demand_rate(item, shops):
    """Shahar shu mahsulotdan bir qadamda qancha yutadi (do'kon + markaz)."""
    rate = 0.0
    for name in shops or ():
        items = SHOPS.get(name)
        if items and item in items:
            rate += (2 if len(items) == 1 else 1) / SHOP_SELL_INTERVAL
    if item != "FERTILIZER":
        rate += 1.0 / TOWN_CENTER_INTERVAL
    return rate

# --- Sozlanadigan parametrlar ---
MAX_WORK_DIST = 5
MAX_WORK_DIST_LATE = 6    # o'lchangan: yangi 8 seedda 81,526 -> 90,277, min 42k -> 78k
EXPAND_DAY = 8            # (kun 6: o'rtacha teng, lekin min ancha yomon)
CENTER_REGION = False     # o'lchangan: markazdan hudud yomonroq (31,723 vs 72,411)
MAX_LAND_BUYS = 1
MAX_HANDS_CAP = 10
# Ishchi narxi fib(n): 11-chisi $89, 12-chisi $144/kun. Mavsum boshida bu qimmat,
# lekin oxirida bankda $70k bo'lganda arzon. Pul yetganda limitni ko'taramiz.
HANDS_MONEY_GATE = 999999   # shu puldan oshsa MAX_HANDS_LATE ishlaydi
MAX_HANDS_LATE = 10
MIN_HANDS = 4
TILES_PER_UNIT = 2
MIN_CASH_BUFFER = 100
HIRE_BY_CASH = False      # o'lchangan: erta ishchi zarar (45,186 vs 72,411)
HIRE_CASH_RESERVE = 1500  # ishchidan keyin hayvonga qoladigan pul
CARRY_BEFORE_DROP = 8
MAX_MARKET_ORDERS = 10

# CHORVA — v5 ning asosi.
#   COW   $400, 1.50 birlik/kun x $160 = $240/kun -> 1.7 kunda qoplanadi
#   SHEEP $500, 1.33 birlik/kun x $200 = $267/kun -> 1.9 kunda qoplanadi
#   GOOSE $300, 2.00 birlik/kun x $50  = $100/kun -> 3.0 kunda qoplanadi
# Hayvon EKINDAN ustun: bir marta joylashtiriladi va qayta ekish kerak emas,
# ya'ni birlik-qadam sarfi kam. Cheklov — FEED va CARE uchun ishchi vaqti.
N_ANIMAL_TILES = 14
ANIMAL_PLAN_SIZE = 20     # reja bo'yicha jami hayvon soni
GOOSE_SHARE = 4           # shundan nechtasi g'oz (EGG bozori alohida talabga ega)


def _plan():
    """Reja: sigir/qo'y navbatma-navbat (eng yuqori $/kun), oxirida g'ozlar."""
    n_big = max(0, ANIMAL_PLAN_SIZE - GOOSE_SHARE)
    big = [("COW" if i % 2 == 0 else "SHEEP") for i in range(n_big)]
    return big + ["GOOSE"] * GOOSE_SHARE
ANIMAL_LAST_DAY = 22      # bundan keyin hayvon olish qoplanmaydi
ANIMAL_MIN_CASH = 500     # hayvon olishdan keyin qolishi kerak bo'lgan ish kapitali
LAND_MIN_DAY = 4          # yer faqat daromad oqimi boshlangach olinadi
PREMIUM_SEED_MIN_CASH = 900    # o'lchangan: qulupnay urug'ini ERTA olish muhim
                               # (79,630 vs 76,106). Qulupnay 10 kunda hosil
                               # beradi, kech ekilsa mavsumga ulgurmaydi.
WORKING_CASH = 250        # har qanday investitsiyadan keyin qoladigan zaxira
FEED_CARRY = 6
# FERTILIZE: 1 dona go'ng + sug'orish = ongoing ekin hosili IKKI BAROBAR,
# 3 kun davomida. Go'ng hayvonlardan bepul yig'iladi. Shu paytgacha uni faqat
# sotardik — bu esa ekin daromadini ikki barobarlashtirish imkonini beradi.
FERT_RESERVE = 3          # birlik qo'lida ushlab turadigan go'ng (tashlanmaydi)
USE_FERTILIZE = False     # o'lchangan: go'ngni SOTISH foydaliroq (81,383 vs 75,122)
FEED_BUY_DAYS = 3
# Oziq bug'doyi ombordan shuncha joydan ko'p egallamasligi kerak. Ombor sig'imi
# 100 va ortig'i kun oxirida YO'Q QILINADI. Bug'doyni umuman sotmasak, u omborni
# to'ldirib butun hosilni siqib chiqaradi (o'lchangan: radius 7 da 100/100 band).
WHEAT_SHED_CAP = 45         # omborda shuncha kunlik oziq zaxirasi saqlanadi
FEED_FROM_MARKET = True   # oziq bozordan olinadi -> bug'doy SOTILMAYDI
COLLECT_FERT = True       # go'ng yig'ish (shahar talabi NOL, faqat bozorga sotiladi)
SELL_PRICE_FLOOR = 0.60   # narx bazaning shu ulushidan pastga tushsa sotilmaydi
SELL_CHUNK = 20           # top o'yinchi logida SELL ITEM 1000 kabi katta son
                          # so'raladi, dvijok mavjud miqdorga kesib qo'yadi —
                          # kichik SELL_CHUNK=3 keraksiz sekinlashtirar edi
                          # (o'lchangan: 92,024 -> 93,868)
DUMP_FROM_DAY = 28        # mavsum oxirida hammasi sotiladi

LAND_PRICES = [1000, 2000, 4000]
LAND_LAST_DAY = [20, 18, 15]
LAND_CASH_RESERVE = 400

# Bir nechta aralashma varianti; CROP_MIX_ID bilan tanlanadi (sweep uchun).
# Eslatma: narxlar bazadan YUQORI turibdi (shahar talabi sotuvimizdan ko'p),
# shuning uchun qimmat ekinlarni ko'proq ekish mantiqan to'g'ri.
CROP_MIXES = {
    0: ["WHEAT"] * 10,                                        # faqat bug'doy (v3 uslubi)
    1: ["WHEAT", "WHEAT", "WHEAT", "CARROT", "WHEAT", "TOMATO",
        "WHEAT", "STRAWBERRY", "WHEAT", "MELON"],             # bug'doy ustunlik qiladi
    2: ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "WHEAT",
        "MELON", "STRAWBERRY", "TOMATO", "WHEAT", "MELON"],   # muvozanatli
    3: ["STRAWBERRY", "MELON", "TOMATO", "STRAWBERRY", "MELON",
        "TOMATO", "STRAWBERRY", "WHEAT", "MELON", "WHEAT"],   # qimmat ekinlar ustun
    4: ["STRAWBERRY", "TOMATO", "STRAWBERRY", "TOMATO",
        "STRAWBERRY", "TOMATO", "STRAWBERRY", "MELON"],       # faqat ongoing + melon
    5: ["MELON", "MELON", "MELON", "MELON", "WHEAT",
        "MELON", "MELON", "MELON", "MELON", "WHEAT"],         # deyarli faqat qovun
    6: ["MELON", "MELON", "WHEAT", "MELON", "CARROT",
        "MELON", "MELON", "WHEAT", "MELON", "CARROT"],        # qovun + tez arzon to'ldiruvchi
    7: ["MELON", "MELON", "MELON", "STRAWBERRY", "MELON",
        "MELON", "MELON", "TOMATO", "MELON", "WHEAT"],        # qovun ustun, ozgina ongoing
    8: ["MELON"] * 9 + ["WHEAT"],                              # sof qovun
    9: ["MELON", "MELON", "MELON", "MELON", "MELON",
        "MELON", "MELON", "MELON", "MELON", "MELON"],         # 100% qovun
    10: ["MELON", "MELON", "MELON", "WHEAT",
         "MELON", "MELON", "MELON", "WHEAT"],                 # 3:1 qovun:bug'doy
}
CROP_MIX_ID = 5   # o'lchangan 8 seedda: 92,024 (mix3: 88,969, mix9-sof qovun: 92,020
                  # lekin min 76,696 - beqaror; mix5 ustunroq: min 85,392)
CROP_MIX = CROP_MIXES[CROP_MIX_ID]


def _fib(n):
    a, b = 1, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def _dist(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _shed_dist(pos):
    """Eng yaqin ombor kirishigacha masofa.

    Ishchilar ombor kirishlarida (markazda) tug'iladi, ya'ni to'rtala chorak
    ham ular uchun teng. Hududni bitta burchakdan o'lchash sun'iy ravishda
    bir tomonga og'diradi."""
    return min(_dist(pos, t) for t in SHED_TILES)


def _nearest_shed(pos):
    """Omborning 4 ta kirish tile'idan eng yaqini."""
    return min(SHED_TILES, key=lambda t: (_dist(pos, t), t))


def _step_toward(pos, target):
    x, y = pos
    tx, ty = target
    if x < tx:
        return ["EAST"]
    if x > tx:
        return ["WEST"]
    if y < ty:
        return ["SOUTH"]
    if y > ty:
        return ["NORTH"]
    return None


def _inv_count(inv, item):
    if not inv:
        return 0
    v = inv.get(item, 0)
    return v if isinstance(v, int) else 0


def _load(inv, wheat_reserve=0):
    """Omborga tashiladigan yuk.

    Hisobga KIRMAYDI:
      * hayvon — tashlab yuborilsa joylashtirish sikli tugamaydi;
      * `wheat_reserve` donagacha bug'doy — u hayvonlarni oziqlantirish uchun
        olib yurilgan; qaytarib tashlansa hayvonlar ochlikdan qochib ketadi.
    """
    if not inv:
        return 0
    total = 0
    for k, v in inv.items():
        if not isinstance(v, int) or v <= 0 or k in ANIMALS:
            continue
        if k == "WHEAT":
            v = max(0, v - wheat_reserve)
        elif k == "FERTILIZER" and USE_FERTILIZE:
            v = max(0, v - FERT_RESERVE)
        total += v
    return total


def _carried_animal(inv):
    if not inv:
        return None
    for a in ANIMALS:
        if _inv_count(inv, a) > 0:
            return a
    return None


def _radius(day):
    # Erta kunlarda pul hayvonga ketishi kerak; keng radius uni ekin urug'iga
    # sarflab yuboradi. Daromad oqimi boshlangach hudud kengayadi.
    return MAX_WORK_DIST_LATE if day >= EXPAND_DAY else MAX_WORK_DIST


def _layout(tiles, day):
    """Ish radiusidagi tile'larni rollarga bo'ladi: hayvon tile'lari + ekin tile'lari."""
    cand = []
    for y, row in enumerate(tiles):
        for x, t in enumerate(row):
            if t == "LOCKED" or (x, y) in SHED_TILES:
                continue
            d = _shed_dist((x, y)) if CENTER_REGION else _dist((x, y), ANCHORS[DROP_ANCHOR])
            if d <= _radius(day):
                cand.append((d, (x, y)))
    cand.sort()
    positions = [p for _, p in cand]
    # Hayvonlar omborga eng yaqin tile'larda: har kuni FEED/CARE kerak
    animal_pos = positions[:N_ANIMAL_TILES]
    crop_pos = positions[N_ANIMAL_TILES:]
    return animal_pos, crop_pos


def _crop_for(idx, day):
    """Tile indeksiga qarab ekin tanlaydi; ulgurmaydigan ekin ekilmaydi."""
    mix = CROP_MIXES[CROP_MIX_ID]
    crop = mix[idx % len(mix)]
    if day > SEASON_DAYS - CROPS[crop]["first"] - 1:
        # Bu ekin ulgurmaydi — tez pishadiganiga o'tamiz
        for alt in ("CARROT", "WHEAT"):
            if day <= SEASON_DAYS - CROPS[alt]["first"] - 1:
                return alt
        return None
    return crop


def _build_tasks(obs, me, tiles, day, seeds, shed, shops=None, prices=None):
    """(ustuvorlik, pozitsiya, amal, talab) ro'yxati. Talab: None yoki 'WHEAT'."""
    tasks = []
    animal_pos, crop_pos = _layout(tiles, day)
    animal_set = set(animal_pos)
    late = day >= SEASON_DAYS - 2

    for y, row in enumerate(tiles):
        for x, t in enumerate(row):
            pos = (x, y)
            if t == "LOCKED" or pos in SHED_TILES:
                continue
            if (_shed_dist(pos) if CENTER_REGION else _dist(pos, ANCHORS[DROP_ANCHOR])) > _radius(day):
                continue

            if isinstance(t, dict):
                kind = t.get("kind")
                if "animal" in t:
                    # Oziqlantirish kritik: 2 kun qoldirilsa hayvon qochadi
                    if not t.get("fed_today", False):
                        tasks.append((-2, pos, ["FEED"], "WHEAT"))   # hayvon o'limi = $300 aktiv yo'qolishi
                    if t.get("yield_units", 0) > 0:
                        tasks.append((-1, pos, ["HARVEST"], None))
                    if not t.get("cared_today", False):
                        tasks.append((2, pos, ["CARE"], None))
                    if COLLECT_FERT and t.get("fertilizer_available", False):
                        tasks.append((3, pos, ["COLLECT_FERTILIZER"], None))
                    continue
                if kind == "WEED":
                    tasks.append((2, pos, ["DIG"], None))
                    continue
                if kind == "PLANT":
                    crop = t.get("crop", "WHEAT")
                    cd = CROPS.get(crop, CROPS["WHEAT"])
                    age = day - t.get("planted_day", day)
                    yield_units = t.get("yield_units", 0)
                    ready = age >= cd["first"] and yield_units > 0
                    if ready and (age >= cd["max_day"] or late or cd["ongoing"]):
                        tasks.append((1, pos, ["HARVEST"], None))
                    elif not t.get("watered_today", False):
                        tasks.append((0, pos, ["WATER"], None))
                    elif (USE_FERTILIZE and cd["ongoing"]
                          and t.get("fertilized_until_day", -1) < day
                          and day <= SEASON_DAYS - 2):
                        # Sug'orilgan ongoing ekin — o'g'it hosilni 2x qiladi
                        tasks.append((1, pos, ["FERTILIZE"], "FERTILIZER"))
                    continue
                if kind in ("COOP", "PASTURE"):
                    # Bo'sh struktura — mos hayvon omborda bo'lsa joylashtiramiz
                    placed_any = False
                    for a, ad in ANIMALS.items():
                        if ad["structure"] == kind and shed.get(a, 0) > 0:
                            tasks.append((-1, pos, ["PLACE", a], a))
                            placed_any = True
                            break
                    # EKIN tile'ida qolib ketgan bo'sh struktura ekishni to'sadi.
                    # Bunday strukturalar NW yolg'iz ochiq paytda qurilgan, NE
                    # ochilgach esa hudud kengayib, ular ekin zonasiga tushgan.
                    if not placed_any and pos not in animal_set:
                        tasks.append((3, pos, ["DIG"], None))
                    continue

            if t is None:
                if pos in animal_set:
                    # Hayvon uchun struktura qurish
                    want = _next_animal(tiles, day, shops, prices)
                    if want:
                        op = "BUILD_COOP" if ANIMALS[want]["structure"] == "COOP" else "BUILD_PASTURE"
                        tasks.append((2, pos, [op], None))
                    continue
                idx = crop_pos.index(pos) if pos in crop_pos else 0
                crop = _crop_for(idx, day)
                if not crop or seeds.get(crop, 0) <= 0:
                    # Rejadagi ekinning urug'i yo'q — tile bo'sh turmasin,
                    # urug'i bor va ulgurادigan boshqa ekinni ekamiz.
                    crop = None
                    for alt, cd in CROPS.items():
                        if (seeds.get(alt, 0) > 0
                                and day <= SEASON_DAYS - cd["first"] - 1):
                            crop = alt
                            break
                if crop and seeds.get(crop, 0) > 0:
                    tasks.append((2, pos, ["PLANT", crop], None))
    return tasks


def _count_animals(tiles):
    have = {}
    structs = {"COOP": 0, "PASTURE": 0}
    for row in tiles:
        for t in row:
            if isinstance(t, dict):
                if "animal" in t:
                    have[t["animal"]] = have.get(t["animal"], 0) + 1
                elif t.get("kind") in structs:
                    structs[t["kind"]] += 1
    return have, structs


def _owned_animals(tiles, shed, invs):
    """Hayvonlar uch joyda bo'lishi mumkin: tile'da, omborda, birlik qo'lida.
    Faqat bittasini sanash ikki xatoga olib keladi: ortiqcha sotib olish va
    oziq zaxirasini noto'g'ri hisoblash."""
    placed, _ = _count_animals(tiles)
    owned = dict(placed)
    for a in ANIMALS:
        n = shed.get(a, 0)
        if isinstance(n, int) and n > 0:
            owned[a] = owned.get(a, 0) + n
        for inv in invs:
            owned[a] = owned.get(a, 0) + _inv_count(inv, a)
    return {k: v for k, v in owned.items() if v > 0}


def _next_animal(tiles, day, shops=None, prices=None):
    """Rejadagi navbatdagi hayvon. Agar unga struktura qurib bo'lmasa (bo'sh tile
    qolmagan), mavjud bo'sh strukturaga mos hayvonni tanlaydi — aks holda reja
    tiqilib qoladi."""
    if day > ANIMAL_LAST_DAY:
        return None
    have, structs = _count_animals(tiles)
    counts = dict(have)
    pending = None
    for a in _plan():
        if counts.get(a, 0) > 0:
            counts[a] -= 1
        else:
            pending = a
            break
    if pending is None:
        return None

    if ADAPT_TO_SHOPS and shops is not None:
        # Mavjud bo'sh strukturaga mos hayvonlardan eng foydalisini tanlaymiz.
        # Qiymat = shahar talab tezligi x joriy narx. Talabsiz mahsulot
        # ishlab chiqarish narxni polga tushiradi va pul yonadi.
        cands = []
        for a, ad in ANIMALS.items():
            if structs.get(ad["structure"], 0) <= 0:
                continue
            prod = ad["product"]
            price = (prices or {}).get(prod, BASE_PRICE[prod])
            # QOPLANMAGAN talab: shahar yutadigan tezlikdan bizning ishlab
            # chiqarishimizni ayiramiz. Faqat narxga qarasak agent bitta
            # mahsulotga yopishib qoladi va uning narxini polga tushiradi
            # (o'lchangan: 17 qo'y, jun $31, sut esa $275 da sotilmagan).
            our_rate = have.get(a, 0) * ANIMAL_RATE[a] / 24.0
            headroom = _demand_rate(prod, shops) - our_rate
            cands.append((headroom * price, a))
        cands.sort(reverse=True)
        if cands and cands[0][0] > 0:
            return cands[0][1]
        if cands:
            return None        # hamma mahsulot to'yingan — yangi hayvon zarar

    if structs.get(ANIMALS[pending]["structure"], 0) > 0:
        return pending
    # Rejadagi hayvonga struktura yo'q — bo'sh strukturaga mos boshqasini olamiz
    for a, ad in ANIMALS.items():
        if structs.get(ad["structure"], 0) > 0:
            return a
    return pending


def _assign(units, invs, tasks, wheat_reserve=0, shed=None):
    ops = [None] * len(units)
    taken = set()
    loads = [_load(i, wheat_reserve) for i in invs]

    # HAYVON TASHISH BIRINCHI O'RINDA.
    # DROP butun inventarni to'kadi — shu jumladan ko'tarib ketayotgan hayvonni.
    # Agar yuk tekshiruvi oldin kelsa, hayvon omborga qaytib tushadi va sikl
    # cheksiz takrorlanadi: sotib olingan hayvon hech qachon joylashmaydi,
    # reja kvotasini band qilib turadi va pul yonadi (o'lchangan: 20 dan 5 tasi).
    for i, pos in enumerate(units):
        a = _carried_animal(invs[i])
        if not a:
            continue
        spots = [t[1] for t in tasks if t[2][0] == "PLACE" and t[2][1] == a]
        if spots:
            tgt = min(spots, key=lambda q: _dist(pos, q))
            ops[i] = ["PLACE", a] if pos == tgt else (_step_toward(pos, tgt) or ["PLACE", a])

    # Yuki to'lgan birliklar omborga
    for i, pos in enumerate(units):
        if ops[i] is None and loads[i] >= CARRY_BEFORE_DROP:
            ops[i] = (["DROP"] if pos in SHED_TILES
                      else _step_toward(pos, _nearest_shed(pos)) or ["DROP"])

    free = [i for i in range(len(units)) if ops[i] is None]

    # OMBORDAGI HAYVONNI OLIB CHIQISH — oziq yetkazuvchilardan OLDIN.
    # Ilgari bu ro'yxat oxirida turardi va unga bo'sh birlik qolmasdi:
    # sotib olingan hayvon omborda yotib qolar, reja kvotasini band qilar va
    # daromad keltirmasdi (o'lchangan: 20 dan 5 tasi 16 kun davomida omborda).
    if shed:
        for a in ANIMALS:
            n = shed.get(a, 0)
            if not isinstance(n, int) or n <= 0:
                continue
            spots = sum(1 for t in tasks if t[2][0] == "PLACE" and t[2][1] == a)
            carried = sum(1 for inv in invs if _inv_count(inv, a) > 0)
            for _ in range(max(0, min(n, spots) - carried)):
                if not free:
                    break
                i = min(free, key=lambda j: _dist(units[j], _nearest_shed(units[j])))
                sp = _nearest_shed(units[i])
                ops[i] = (["PICKUP", a, 1] if units[i] in SHED_TILES
                          else _step_toward(units[i], sp) or ["PASS"])
                free.remove(i)

    # OZIQ YETKAZUVCHILARNI OLDINDAN AJRATISH.
    # Aks holda birliklar CARE/COLLECT_FERTILIZER kabi past ustuvorlikdagi
    # ishlarga tarqalib ketadi va omborga bug'doy olib boradigan hech kim
    # qolmaydi -> hayvonlar kun oxirigacha och qoladi va qochib ketadi.
    n_unfed = sum(1 for t in tasks if t[2][0] == "FEED")
    if n_unfed:
        carried = sum(1 for i in free if _inv_count(invs[i], "WHEAT") > 0)
        need_carriers = -(-(n_unfed - carried * FEED_CARRY) // FEED_CARRY)
        for _ in range(max(0, need_carriers)):
            cands = [i for i in free if _inv_count(invs[i], "WHEAT") == 0]
            if not cands:
                break
            i = min(cands, key=lambda j: _dist(units[j], _nearest_shed(units[j])))
            if units[i] in SHED_TILES:
                ops[i] = ["PICKUP", "WHEAT", FEED_CARRY]
            else:
                ops[i] = _step_toward(units[i], _nearest_shed(units[i])) or ["PASS"]
            free.remove(i)

    order = sorted(range(len(tasks)), key=lambda k: tasks[k][0])

    unfed_unserved = 0
    missing = set()          # ombordan olib kelish kerak bo'lgan narsalar
    for k in order:
        if not free:
            break
        prio, tpos, op, need = tasks[k]
        key = (tpos, op[0])
        if key in taken:
            continue
        # Talabni bajara oladigan birliklar
        if need:
            able = [i for i in free if _inv_count(invs[i], need) > 0]
            if not able:
                if op[0] == "FEED":
                    unfed_unserved += 1
                else:
                    missing.add(need)   # masalan GOOSE: omborda bor, qo'lda yo'q
                continue
        else:
            able = free
        best = min(able, key=lambda i: _dist(units[i], tpos))
        if units[best] == tpos:
            ops[best] = op
        else:
            mv = _step_toward(units[best], tpos)
            if mv is None:
                continue
            ops[best] = mv
        taken.add(key)
        free.remove(best)

    # Omborga borib kerakli narsani olib kelish.
    # Hayvon birinchi navbatda: u joylashtirilmasa umuman daromad bermaydi.
    fetch = [m for m in missing if m in ANIMALS]
    if unfed_unserved:
        # Bitta birlik FEED_CARRY donagacha olib keladi. Och hayvon ko'p bo'lsa
        # bitta yetkazuvchi yetmaydi — shuncha birlikni yuboramiz.
        n_carriers = max(1, -(-unfed_unserved // FEED_CARRY))
        fetch.extend(["WHEAT"] * n_carriers)
    for item in fetch:
        if not free:
            break
        i = min(free, key=lambda j: _dist(units[j], _nearest_shed(units[j])))
        if units[i] in SHED_TILES:
            n = FEED_CARRY if item == "WHEAT" else 1
            ops[i] = ["PICKUP", item, n]
        else:
            ops[i] = _step_toward(units[i], _nearest_shed(units[i])) or ["PASS"]
        free.remove(i)

    for i in free:
        if loads[i] > 0:
            ops[i] = (["DROP"] if units[i] in SHED_TILES
                      else _step_toward(units[i], _nearest_shed(units[i])) or ["DROP"])
        else:
            ops[i] = _step_toward(units[i], _nearest_shed(units[i])) or ["PASS"]

    return [op if op else ["PASS"] for op in ops]


def _sell_orders(shed, prices, day, market, feed_reserve=0):
    """Narxga qarab sotish. Hajmga chidamlilar cheklovsiz, qolganlari ehtiyot bilan."""
    total = sum(v for v in shed.values() if isinstance(v, int))
    overflowing = total > SHED_CAPACITY * 0.8
    dump = day >= DUMP_FROM_DAY or overflowing

    for item, qty in sorted(shed.items(), key=lambda kv: -BASE_PRICE.get(kv[0], 0) * (kv[1] or 0)):
        if len(market) >= MAX_MARKET_ORDERS - 2:
            break
        if not isinstance(qty, int) or qty <= 0 or item not in BASE_PRICE:
            continue
        if item == "WHEAT":
            # Bug'doy bu yerda TOVAR emas, OZIQ — sotilsa hayvonlar och qoladi.
            # (Ombor tiqilishini WHEAT_SHED_CAP sotib olish tomonidan cheklaydi.)
            if FEED_FROM_MARKET:
                continue
            qty -= feed_reserve
            if qty <= 0:
                continue
        if dump or item in GLUT_PROOF:
            market.append(["SELL", item, qty])
            continue
        price = prices.get(item, BASE_PRICE[item])
        if price >= BASE_PRICE[item] * SELL_PRICE_FLOOR:
            market.append(["SELL", item, min(qty, SELL_CHUNK)])


def _agent(obs):
    me = obs["farms"][obs["player"]]
    private = obs["private"]
    day = obs["day"]
    tiles = me["tiles"]
    shed = dict(private.get("shed", {}))
    seeds = dict(private.get("seeds", {}))
    prices = dict(obs["market"]["prices"])
    invs = list(private.get("inventories", []))

    units = [tuple(me["farmer"])] + [tuple(h) for h in me.get("hands", [])]
    while len(invs) < len(units):
        invs.append({})

    shops = list(obs["town"].get("unlocked_shops", []))
    tasks = _build_tasks(obs, me, tiles, day, seeds, shed, shops, prices)
    owned = _owned_animals(tiles, shed, invs)
    n_owned = sum(owned.values())
    wheat_reserve = FEED_CARRY if n_owned else 0
    ops = _assign(units, invs, tasks, wheat_reserve, shed)

    # --- Bozor ---
    market = []
    budget = me["money"]

    _sell_orders(shed, prices, day, market, feed_reserve=n_owned * 4)

    # --- Investitsiya siyosati: tartib muhim ---
    # Kun 0 da hamma narsani birdan sotib olish agentni bankrot qiladi.
    # Ketma-ketlik: urug' (dvigatel) -> hayvon (tez qoplanadi) -> yer (sekin).

    # 1) Arzon urug'lar — bularsiz ferma to'xtaydi
    need = {}
    _, crop_pos = _layout(tiles, day)
    for i, pos in enumerate(crop_pos):
        x, y = pos
        if tiles[y][x] is None:
            c = _crop_for(i, day)
            if c:
                need[c] = need.get(c, 0) + 1
    for crop, n in sorted(need.items(), key=lambda kv: CROPS[kv[0]]["seed"]):
        if len(market) >= MAX_MARKET_ORDERS - 2:
            break
        short = n + 2 - seeds.get(crop, 0)
        if short <= 0:
            continue
        cost = CROPS[crop]["seed"] * short
        # Qimmat urug'ni faqat pul yetarli bo'lganda olamiz
        floor = PREMIUM_SEED_MIN_CASH if CROPS[crop]["seed"] >= 50 else WORKING_CASH
        if budget - cost >= floor:
            market.append(["BUY_SEED", crop, short])
            budget -= cost

    # 2) Hayvon — bo'sh mos struktura tayyor va omborda hech qanday hayvon yo'q bo'lsa.
    #    G'oz ~3 kunda qoplanadi, shuning uchun yerdan oldin turadi.
    want = _next_animal(tiles, day, shops, prices)
    if want and len(market) < MAX_MARKET_ORDERS:
        _, structs = _count_animals(tiles)
        # Yo'lda turganlar: omborda yoki birlik qo'lida, hali joylashtirilmagan
        in_transit = sum(shed.get(a, 0) for a in ANIMALS) + sum(
            _inv_count(inv, a) for a in ANIMALS for inv in invs)
        free_structs = structs.get(ANIMALS[want]["structure"], 0)
        if (free_structs > in_transit                 # joylashtiradigan joy bor
                and sum(owned.values()) < ANIMAL_PLAN_SIZE
                and budget - ANIMALS[want]["cost"] >= ANIMAL_MIN_CASH):
            market.append(["BUY_ANIMAL", want, 1])
            budget -= ANIMALS[want]["cost"]

    # 2b) Oziq bozordan. Hayvon kuniga ~$240 keltiradi, 1 bug'doy ~$25-50 turadi.
    #     O'zimiz bug'doy ekkandan ko'ra sotib olgan arzon: tile va ishchi tejaladi.
    if n_owned and len(market) < MAX_MARKET_ORDERS:
        have_wheat = shed.get("WHEAT", 0)
        want_wheat = n_owned * FEED_BUY_DAYS
        short = want_wheat - (have_wheat if isinstance(have_wheat, int) else 0)
        if short > 0:
            price = prices.get("WHEAT", 25)
            cost = price * short
            if budget - cost >= WORKING_CASH:
                market.append(["BUY_PRODUCT", "WHEAT", short])
                budget -= cost

    # 3) Yer — eng sekin qoplanadigani, oxirida
    n_bought = max(0, len(me.get("unlocked_quadrants", ["NW"])) - 1)
    if (n_bought < min(MAX_LAND_BUYS, len(LAND_PRICES))
            and LAND_MIN_DAY <= day <= LAND_LAST_DAY[n_bought]
            and budget - LAND_PRICES[n_bought] >= LAND_CASH_RESERVE
            and len(market) < MAX_MARKET_ORDERS):
        market.append(["BUY_LAND"])
        budget -= LAND_PRICES[n_bought]

    # Ishchi
    n_open = len([1 for y, row in enumerate(tiles) for x, t in enumerate(row)
                  if t != "LOCKED" and (x, y) not in SHED_TILES
                  and (_shed_dist((x, y)) if CENTER_REGION else _dist((x, y), ANCHORS[DROP_ANCHOR])) <= _radius(day)])
    cap = MAX_HANDS_LATE if me["money"] >= HANDS_MONEY_GATE else MAX_HANDS_CAP
    # Ishchi soni tile'ga ham, PULGA ham qarab belgilanadi. Ilgari faqat tile
    # hisoblanardi: mavsum boshida NW yolg'iz ochiq bo'lgani uchun 5 ta ishchi
    # yollanar va $3000 ning katta qismi ishlatilmay qolardi.
    by_tiles = -(-n_open // TILES_PER_UNIT)
    by_cash = MIN_HANDS
    if HIRE_BY_CASH:
        budget_for_hands = max(0, me["money"] - HIRE_CASH_RESERVE)
        acc = 0
        while by_cash < cap:
            acc += _fib(by_cash)
            if acc > budget_for_hands:
                break
            by_cash += 1
    target_hands = max(MIN_HANDS, min(cap, max(by_tiles, by_cash)))
    n = int(me.get("hires_today", 0))
    while n < target_hands and len(market) < MAX_MARKET_ORDERS:
        cost = _fib(n)
        if budget - cost < MIN_CASH_BUFFER:
            break
        market.append(["HIRE"])
        budget -= cost
        n += 1

    return {"farmer": ops[0], "hands": ops[1:], "market": market[:MAX_MARKET_ORDERS]}


def agent(obs):
    try:
        return _agent(obs)
    except Exception:
        return {"farmer": ["PASS"], "hands": [], "market": []}
