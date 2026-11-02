#!/data/data/com.termux/files/usr/bin/bash
# Установка на Android-телефон через Termux (F-Droid версия).
# Запуск:  bash setup-termux.sh
set -e
cd "$(dirname "$0")"
pkg update -y
# rust нужен, чтобы pip собрал pydantic-core (зависимость anthropic)
pkg install -y python git rust binutils termux-api tmux
python -m pip install --upgrade pip
python -m pip install -r tgbot/requirements.txt
mkdir -p inbox/telegram inbox/biz out/timetable out/plan
[ -f .env ] || cp .env.example .env
echo
echo "Готово. Дальше:"
echo "  1) nano .env   — вставьте TELEGRAM_BOT_TOKEN (и при желании ANTHROPIC_API_KEY)"
echo "  2) bash tgbot/run.sh   — бот запустится в фоне (tmux) и не уснёт"
