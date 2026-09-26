# Farmer — Kaggriculture self-play

Окружение для соревнования [Kaggriculture](https://www.kaggle.com/competitions/kaggriculture):
агент учится, играя сам с собой (self-play + генетическая эволюция параметров), каждое поколение
сохраняется в `avlod/`, а тесты проверяют, что агент соответствует правилам соревнования.

Игры идут на **официальном движке** `kaggle_environments` (`kaggriculture`, 2 игрока, 720 ходов,
$3000 на старте, побеждает тот, у кого больше денег в конце).

## Структура

```
agents/base/main.py     параметрический агент (шаблон; PARAMS + PARAM_BOUNDS)
agents/v8/main.py       <- сюда ваш v8 (см. agents/v8/README.md)
agents/v9/main.py       рекомендуемый сабмит: новая base-логика + лучшее поколение avlod_v9/
avlod_v9/               эволюция v9 (против себя, прошлых чемпионов, v8, старого avlod/best и на 4 размерах поля)
trainer/evolve.py       self-play эволюция
trainer/common.py       загрузка агентов как на Kaggle, игры, рендер PARAMS
avlod/avlod_NNN/        поколение N: main.py (готов к сабмиту), params.json, stats.json
avlod/best/             лучший агент (продвигается, только если обыграл прежнего лучшего)
avlod/history.csv       прогресс по поколениям
avlod/population.json   состояние популяции для --resume
tests/test_competition.py  проверки правил соревнования
scripts/make_submission.py сборка submission/main.py и submission.tar.gz
scripts/benchmark.py    сравнение агентов на 5x5 / 5x10 / 5x10+5x5 / 10x10, дуэли, "призрак" из реплея Kaggle
scripts/visualize.py    HTML-отчёты: игра, реплей Kaggle (episode), прогресс обучения
```

## Установка

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

## Обучение

```bash
python -m trainer.evolve --generations 30 --pop 12 --workers 4     # новый запуск
python -m trainer.evolve --resume --generations 30                 # продолжить с последнего avlod
python -m trainer.evolve --agent agents/v8/main.py --fresh --out avlod_v8   # эволюционировать сам v8
```

**Эволюция v8.** В v8 нет словаря `PARAMS` — его настройки обычные константы модуля
(`MAX_WORK_DIST = 5`, `SELL_PRICE_FLOOR = 0.60`, ...). Тренер эволюционирует их напрямую:
в каждом поколении меняются **только числа** в этих строках, логика и комментарии v8 остаются
как есть (поколение 0 байт-в-байт совпадает с `agents/v8/main.py`). Какие константы и в каких
границах — задаёт `agents/v8/bounds.json` (уберите имя — константа зафиксируется). Целые
константы остаются целыми. `--out avlod_v8` кладёт поколения в отдельную папку, чтобы не
перезаписать поколения base-агента в `avlod/`.

Каждое поколение:
1. каждый кандидат играет полные партии против других кандидатов (self-play),
   чемпионов прошлых поколений (hall of fame), `agents/v8/main.py` (если есть) и,
   опционально, `starter` (`--games-starter`);
2. fitness = доля побед + бонус за разницу в деньгах;
3. чемпион сохраняется в `avlod/avlod_NNN/`;
4. в `avlod/best/` он попадает, только если выиграл gate-матч у текущего лучшего;
5. следующая популяция = элита + скрещивание + мутации.

После каждого поколения пишется `<out>/progress.html` — графики fitness, денег и win rate.

Полезные флаги: `--games-self`, `--games-hof`, `--games-v8`, `--gate-games`, `--mut-rate`, `--sigma`.

## v9: что исправлено (разбор проигрыша 79,585 vs 96,247)

Партия с Kaggle (эпизод 113630705) сыграна агентом из `avlod/best`. Причины проигрыша и исправления
в `agents/base/main.py`:

* **Овца весь сезон на складе.** После `last_day_SHEEP` загон терял роль, купленное животное
  оставалось в сарае до конца игры. Теперь у каждого купленного животного всегда есть место.
* **Голодная смерть стада.** Агент мог потратить всё до ~$0 на животных/семена и не купить корм —
  коровы убегали. Теперь есть резерв `op_cash`: корм на `wheat_days` + найм на завтра.
* **Продукция без учёта спроса.** Веса ролей были фиксированными (66% пшеницы по ~$30).
  Теперь вес умножается на **прогноз цены**: производство обеих ферм (они публичны) против
  спроса города (центр + открытые магазины) на оставшиеся дни (`horizon`, `price_gain`).
* **Размер поля.** Роли раздаются от сарая наружу (животные ближе, `animal_first`), и засевается
  не больше клеток, чем команда может обслужить (`tiles_per_unit`); земля покупается, только
  если её есть кем обрабатывать (`land_need`, `max_land`).

Результаты на seed, которых не было в обучении (500+):

| | 5x5 | 5x10 | 5x10+5x5 | 10x10 |
|---|---|---|---|---|
| avlod/best (старый), деньги vs starter | 79,036 | 77,959 | 68,966 | 63,455 |
| **agents/v9**, деньги vs starter | **100,792** | **93,054** | **85,094** | **78,597** |
| avlod/best, деньги vs avlod/best | 50,615 | 48,836 | 30,725 | 25,999 |
| **agents/v9**, деньги vs avlod/best | 49,401 | **58,725** | **50,718** | **47,711** |

Дуэли (12 seed x 2 места): v9 vs старый avlod/best — 24/24, v9 vs v8 — 21/24.

## Размеры поля и бенчмарк

Ферма растёт четвертями 5x5: NW открыта всегда, дальше покупаются NE ($1000), SW ($2000), SE ($4000).
`scripts/benchmark.py maps` заставляет агента купить ровно 0/1/2/3 четверти и показывает деньги
на каждом размере поля:

```bash
python scripts/benchmark.py maps --agents avlod/best/main.py agents/v9/main.py --seeds 8
python scripts/benchmark.py duel agents/v9/main.py avlod/best/main.py --seeds 10
python scripts/benchmark.py ghost 113630705.json --agents agents/v9/main.py   # соперник из реплея
```

`ghost` повторяет записанные ходы соперника на том же seed. Пока ваша игра на рынке совпадает с
записанной, это точная копия партии (старый best даёт ровно те же 79,585 vs 96,247); если ваш агент
торгует иначе, цены у соперника меняются, его записанные ходы перестают подходить и счёт
«призрака» уже не показателен.

В эволюции `--games-maps N` добавляет каждому кандидату N игр на принудительных размерах поля
(по кругу 5x5, 5x10, 5x10+5x5, 10x10) против текущего best; в `stats.json` пишется
`champion_money_by_map`.

## Визуализация

```bash
python scripts/visualize.py game                          # agents/v8 vs avlod/best, seed 1
python scripts/visualize.py game --b starter --seed 7 --open
python scripts/visualize.py game --gen 5 --avlod avlod_v8 --b agents/v8/main.py
python scripts/visualize.py game --replay                 # + официальный реплей Kaggle (~15 МБ)
python scripts/visualize.py episode 113630705.json --open   # реплей, скачанный с Kaggle
python scripts/visualize.py progress --dir avlod_v8 --open
```

Отчёт игры (`replays/*.html`, один файл без интернета): деньги по ходам у обоих игроков,
карта фермы по дням с ползунком (культуры, животные, работники, склад, семена), цены рынка
по товарам и статистика действий юнитов и рыночных ордеров.

## Тесты (правила соревнования)

```bash
pytest -q tests/
```

Проверяются `agents/base`, `avlod/best`, последнее поколение, `agents/v8` и `submission/` (если есть):
`main.py` и функция `agent` — последний callable (так Kaggle выбирает агента), только stdlib/numpy импорты,
файл работает отдельно от репозитория, каждое действие валидно (известные операции, одна команда
на каждого нанятого работника, ≤ 10 рыночных ордеров, JSON), полная игра 720 ходов со статусом
`DONE` на обоих местах, время хода < 0.5 с (лимит `actTimeout` = 1 с), победа над `starter`,
и — если есть v8 — что `avlod/best` обыгрывает v8.

Свой файл можно проверить так: `KAGG_AGENTS=path/to/main.py pytest -q tests/`.

## Сабмит

```bash
python scripts/make_submission.py --src agents/v9/main.py   # рекомендуемый
python scripts/make_submission.py            # из avlod/best (или --gen 7, --avlod avlod_v9)
pytest -q tests/
kaggle competitions submit kaggriculture -f submission/main.py -m "avlod best"
```


