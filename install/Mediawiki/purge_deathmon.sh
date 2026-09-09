#!/bin/bash
set -euo pipefail

# Минимальный скрипт логина ботом + принудительного purge с каскадом на
# все transcluding-страницы. Использует один cookie-файл (curl сам его
# создаёт и читает через -c/-b) - вручную ничего парсить не нужно, кроме
# одного токена на шаге логина (это обязательный анти-CSRF механизм
# самого MediaWiki, обойти нельзя даже для ботов).

# ==== Настройки - поправить под себя ====
WIKI_API="https://sociowiki.sphynkx.org.ua/api.php"
BOT_USER="purgebot@monitorbot"      # формат: ИмяБота@ИмяПароля (то, что дала Special:BotPasswords)
BOT_PASS="сгенерированный_пароль_бота_сюда"
TARGET_TITLE="Модуль:Deathmon"
COOKIE_JAR="$(mktemp)"

# Гарантированно удаляем cookie-файл при выходе (успешном или нет) -
# сессия бота живёт только на время работы скрипта, ничего не остаётся
# валяться на диске между запусками.
trap 'rm -f "$COOKIE_JAR"' EXIT

# --- Шаг 1: получить login-токен ---
LOGIN_TOKEN=$(curl -s -c "$COOKIE_JAR" \
    "${WIKI_API}?action=query&meta=tokens&type=login&format=json" \
    | grep -oP '"logintoken":"\K[^"]+' | sed 's/\\\\/\\/g')

if [ -z "$LOGIN_TOKEN" ]; then
    echo "ОШИБКА: не удалось получить login-токен. Проверьте URL API и сеть." >&2
    exit 1
fi

# --- Шаг 2: залогиниться, используя токен и тот же cookie-файл ---
LOGIN_RESULT=$(curl -s -b "$COOKIE_JAR" -c "$COOKIE_JAR" \
    --data-urlencode "action=login" \
    --data-urlencode "lgname=${BOT_USER}" \
    --data-urlencode "lgpassword=${BOT_PASS}" \
    --data-urlencode "lgtoken=${LOGIN_TOKEN}" \
    --data-urlencode "format=json" \
    "$WIKI_API")

if ! echo "$LOGIN_RESULT" | grep -q '"result":"Success"'; then
    echo "ОШИБКА: логин не удался. Ответ сервера:" >&2
    echo "$LOGIN_RESULT" >&2
    exit 1
fi

# --- Шаг 3: собственно purge с каскадом на все transcluding-страницы ---
PURGE_RESULT=$(curl -s -b "$COOKIE_JAR" \
    --data-urlencode "action=purge" \
    --data-urlencode "forcerecursivelinkupdate=1" \
    --data-urlencode "titles=${TARGET_TITLE}" \
    --data-urlencode "format=json" \
    "$WIKI_API")

echo "PURGE RESULT: $PURGE_RESULT"
