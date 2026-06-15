import swisseph as swe
from groq import Groq
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from flask import Flask
import threading
import requests
import os
import asyncio
from datetime import datetime, timedelta
import pytz

# ─── НАТАЛЬНАЯ КАРТА ───────────────────────────────────────────────
NATAL = {
    "name": "Олли",
    "planets_natal": {
        "Солнце":    {"sign": "Скорпион", "deg": 234.80, "house": 8,  "status": "эссенц. -5, акцид. 0"},
        "Луна":      {"sign": "Скорпион", "deg": 235.38, "house": 8,  "status": "эссенц. -3, акцид. -7, падение"},
        "Меркурий":  {"sign": "Стрелец",  "deg": 249.65, "house": 9,  "status": "эссенц. -5, акцид. 2, изгнание, Антарес"},
        "Венера":    {"sign": "Скорпион", "deg": 238.77, "house": 8,  "status": "эссенц. -2, акцид. 1, изгнание, Толиман"},
        "Марс":      {"sign": "Близнецы", "deg": 99.22,  "house": 3,  "status": "эссенц. -5, акцид. 1, ретро, Альдебаран"},
        "Юпитер":    {"sign": "Лев",      "deg": 133.33, "house": 6,  "status": "эссенц. 1, акцид. 7"},
        "Сатурн":    {"sign": "Козерог",  "deg": 291.10, "house": 11, "status": "эссенц. 5, акцид. 13, обитель"},
        "Уран":      {"sign": "Козерог",  "deg": 277.23, "house": 10, "status": "эссенц. 5, акцид. 16, обитель"},
        "Нептун":    {"sign": "Козерог",  "deg": 282.60, "house": 11, "status": "эссенц. -5, акцид. 15"},
        "Плутон":    {"sign": "Скорпион", "deg": 227.98, "house": 8,  "status": "эссенц. 5, акцид. -1, обитель"},
        "Сев.Узел":  {"sign": "Водолей",  "deg": 300.25, "house": 11, "status": ""},
        "Лилит":     {"sign": "Стрелец",  "deg": 252.27, "house": 9,  "status": ""},
        "Хирон":     {"sign": "Рак",      "deg": 117.27, "house": 5,  "status": "ретро"},
        "Фортуна":   {"sign": "Рыбы",     "deg": 9.55,   "house": 1,  "status": "акцид. 14"},
    },
    "aspects_natal": [
        "Луна–Венера соединение 3°23 сход.",
        "Солнце–Луна соединение 0°34 расход.",
        "Солнце–Венера соединение 3°57 расход.",
        "Солнце–Плутон соединение 6°49 расход.",
        "Луна–Плутон соединение 7°23 расход.",
        "Меркурий–Марс оппозиция 0°26 расход.",
        "Меркурий–Юпитер трин 3°41 сход.",
        "Юпитер–Плутон квадрат 4°40 сход.",
        "Сатурн–Плутон секстиль 3°7 расход.",
        "Солнце–Сатурн секстиль 3°42 расход.",
        "Марс–Юпитер секстиль 4°7 расход.",
        "Луна–Сатурн секстиль 4°16",
        "Меркурий–Сатурн антис 0°45 расход.",
        "Марс–Сатурн контр-антис 0°20 сход.",
    ],
    "special": "Возничий — Венера. Дорифорий — Плутон. Альмутен — Венера. "
               "Рецепция Сатурн=Уран. Рецепция по терму Венера–Сатурн. "
               "Цепочки по владению: Плутон, Сатурн. Цепочки по изгнанию: Венера.",
}

PLANET_IDS = {
    "Солнце": swe.SUN, "Луна": swe.MOON, "Меркурий": swe.MERCURY,
    "Венера": swe.VENUS, "Марс": swe.MARS, "Юпитер": swe.JUPITER,
    "Сатурн": swe.SATURN, "Уран": swe.URANUS, "Нептун": swe.NEPTUNE,
    "Плутон": swe.PLUTO, "Сев.Узел": swe.TRUE_NODE,
}

SIGNS = ["Овен","Телец","Близнецы","Рак","Лев","Дева",
         "Весы","Скорпион","Стрелец","Козерог","Водолей","Рыбы"]

ASPECTS = {
    "соединение": (0, 8), "оппозиция": (180, 8), "трин": (120, 7),
    "квадрат": (90, 7), "секстиль": (60, 5),
}

def deg_to_sign(deg):
    deg = deg % 360
    idx = int(deg / 30)
    d = deg % 30
    return SIGNS[idx], round(d, 2)

def get_transit_positions(dt_utc):
    jd = swe.julday(dt_utc.year, dt_utc.month, dt_utc.day,
                    dt_utc.hour + dt_utc.minute / 60)
    positions = {}
    for name, pid in PLANET_IDS.items():
        pos, _ = swe.calc_ut(jd, pid)
        sign, deg = deg_to_sign(pos[0])
        retro = pos[3] < 0
        positions[name] = {
            "deg_abs": round(pos[0], 2),
            "sign": sign,
            "deg": deg,
            "retro": retro,
        }
    return positions

def find_aspects(transits):
    hits = []
    orb_transit = 2.0
    for t_name, t_data in transits.items():
        for n_name, n_data in NATAL["planets_natal"].items():
            diff = abs(t_data["deg_abs"] - n_data["deg"]) % 360
            if diff > 180:
                diff = 360 - diff
            for asp_name, (asp_deg, orb) in ASPECTS.items():
                orb_use = min(orb, orb_transit)
                if abs(diff - asp_deg) <= orb_use:
                    exact = round(abs(diff - asp_deg), 2)
                    # определяем сходящийся или расходящийся
                    direction = "сход." if t_data["deg_abs"] < n_data["deg"] else "расход."
                    hits.append({
                        "text": f"транзитный {t_name} {asp_name} натальный {n_name} (орб {exact}°, {direction})",
                        "orb": exact,
                        "direction": direction,
                        "fast_to_slow": t_name in ["Луна", "Меркурий", "Венера", "Солнце", "Марс"]
                                        and n_name in ["Сатурн", "Уран", "Нептун", "Плутон"],
                    })
    # сортируем по орбу, расходящиеся помечаем
    hits.sort(key=lambda x: x["orb"])
    return hits

def format_aspects(hits):
    result = []
    for h in hits:
        note = ""
        if h["direction"] == "расход." and h["orb"] > 0.5:
            note = " [расходящийся — событие уже позади]"
        if h["fast_to_slow"]:
            note += " [быстрая по медленной — фоновый эффект]"
        result.append(h["text"] + note)
    return result

def build_natal_summary():
    lines = ["Натальная карта: Олли, 17.11.1990, 13:20, Астрахань",
             "ASC Рыбы 8°58, MC Стрелец 20°08", ""]
    for p, d in NATAL["planets_natal"].items():
        r = " [ретро]" if "ретро" in d.get("status", "") else ""
        lines.append(f"{p}: {d['sign']} {d['deg']}°, дом {d['house']}{r} ({d['status']})")
    lines += ["", "Натальные аспекты:"] + NATAL["aspects_natal"]
    lines += ["", "Особенности:", NATAL["special"]]
    return "\n".join(lines)

def build_system_prompt():
    natal = build_natal_summary()
    return f"""Ты — профессиональный астролог с 20-летним опытом практики. Работаешь в традиции эллинистической и средневековой астрологии. Твой клиент — Олли, женщина.

{natal}

ЖЁСТКИЕ ПРАВИЛА — нарушение недопустимо:

1. ПРИОРИТЕТЫ ТРАНЗИТОВ:
   — Медленные планеты по натальным точкам (Сатурн, Уран, Нептун, Плутон транзитом) — главное, описывай подробно
   — Юпитер и Марс транзитом — среднее значение
   — Быстрые планеты (Луна, Меркурий, Венера, Солнце) по медленным натальным (Сатурн, Уран, Нептун, Плутон) — незначительный фон, упоминай вскользь или не упоминай вовсе
   — Расходящийся аспект с орбом больше 1° — событие уже произошло, не акцентируй
   — Сходящийся аспект с орбом до 1° — пиковое влияние прямо сейчас, выдели отдельно

2. ФОРМАТ ПРОГНОЗА:
   — Никаких клише: "звёзды благоволят", "будь осторожен", "прекрасное время", "энергия дня"
   — Никакой воды и общих фраз
   — Каждое утверждение = конкретное астрологическое основание
   — Пиши на двух уровнях: психологический (что происходит внутри) и событийный (что может случиться снаружи)
   — Не "плохое настроение" а "возможен конфликт с коллегой или близким — Марс транзитом квадрат натальному Меркурию в 9 доме активирует раздражение в коммуникациях"
   — Язык живой, на "ты", без пафоса и астрологического жаргона там где без него можно обойтись

3. СТРУКТУРА ДНЯ:
   — Одна фраза: общий тон (не абстрактно — конкретно что доминирует)
   — Ключевые транзиты (только значимые, орб до 2°, с приоритетом по правилу выше)
   — Психологический уровень: что ты чувствуешь и почему
   — Событийный уровень: что может произойти конкретно
   — Одна строка: чего лучше не делать и почему астрологически

4. РАЗГОВОРНЫЙ РЕЖИМ:
   — Если пользователь задаёт уточняющий вопрос после прогноза — отвечай по существу, не повторяй прогноз
   — Если спрашивает про конкретную тему (работа, отношения, здоровье) — фокусируйся на домах и планетах связанных с этой темой
   — Если спрашивает про конкретную дату — анализируй транзиты на ту дату

5. ЗАПРЕЩЕНО:
   — Повторять одно и то же в разные дни если планеты не изменились
   — Писать про быстрые транзиты по медленным натальным как про важные события
   — Заканчивать фразами "всё будет хорошо", "доверяй себе", "слушай интуицию"
"""

def generate_forecast(period_label, transits, aspects_raw):
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    transit_text = "\n".join(
        f"{n}: {d['sign']} {d['deg']}°{'[Ретро]' if d['retro'] else ''}"
        for n, d in transits.items()
    )
    formatted = format_aspects(aspects_raw)
    aspect_text = "\n".join(formatted) if formatted else "Значимых аспектов нет."
    user_msg = f"""Составь прогноз на {period_label}.

Транзитные планеты:
{transit_text}

Активные аспекты (отсортированы по орбу, помечены приоритеты):
{aspect_text}

Применяй правила приоритетов строго."""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.7,
        max_tokens=1500,
    )
    return response.choices[0].message.content

def send_chunks(text, chat_id, bot_send_func):
    """Разбивает длинный текст на части по 3800 символов"""
    chunk_size = 3800
    chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
    return chunks

# ─── TELEGRAM ──────────────────────────────────────────────────────
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
conversation_history = []

async def send_daily_forecast(bot):
    now_utc = datetime.utcnow()
    transits = get_transit_positions(now_utc)
    aspects = find_aspects(transits)
    today_str = datetime.now(pytz.timezone("Europe/Moscow")).strftime("%d.%m.%Y")
    text = generate_forecast(today_str, transits, aspects)
    full = f"🌙 Прогноз на {today_str}\n\n{text}"
    for chunk in send_chunks(full, CHAT_ID, None):
        await bot.send_message(chat_id=CHAT_ID, text=chunk)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📅 Сегодня", callback_data="today"),
         InlineKeyboardButton("📅 Завтра", callback_data="tomorrow")],
        [InlineKeyboardButton("📆 Неделя", callback_data="week"),
         InlineKeyboardButton("🗓 Месяц", callback_data="month")],
        [InlineKeyboardButton("📊 Год", callback_data="year"),
         InlineKeyboardButton("📌 Дата", callback_data="custom_date")],
    ]
    await update.message.reply_text(
        "Привет, Олли. Я твой личный астролог.\n\nЧто хочешь узнать?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    now_utc = datetime.utcnow()
    msk = pytz.timezone("Europe/Moscow")

    if query.data == "today":
        transits = get_transit_positions(now_utc)
        aspects = find_aspects(transits)
        label = datetime.now(msk).strftime("%d.%m.%Y")
        await query.edit_message_text("Считаю транзиты...")
        text = generate_forecast(label, transits, aspects)
        full = f"📅 {label}\n\n{text}"
        for chunk in send_chunks(full, query.message.chat_id, None):
            await context.bot.send_message(chat_id=query.message.chat_id, text=chunk)

    elif query.data == "tomorrow":
        day = now_utc + timedelta(days=1)
        transits = get_transit_positions(day)
        aspects = find_aspects(transits)
        label = (datetime.now(msk) + timedelta(days=1)).strftime("%d.%m.%Y")
        await query.edit_message_text("Считаю транзиты...")
        text = generate_forecast(label, transits, aspects)
        full = f"📅 Завтра {label}\n\n{text}"
        for chunk in send_chunks(full, query.message.chat_id, None):
            await context.bot.send_message(chat_id=query.message.chat_id, text=chunk)

    elif query.data == "week":
        await query.edit_message_text("Строю прогноз на неделю...")
        days_data = []
        for i in range(7):
            day = now_utc + timedelta(days=i)
            transits = get_transit_positions(day)
            aspects = find_aspects(transits)
            label = (datetime.now(msk) + timedelta(days=i)).strftime("%d.%m")
            transit_text = "\n".join(
                f"{n}: {d['sign']} {d['deg']}°{'[Ретро]' if d['retro'] else ''}"
                for n, d in transits.items()
            )
            formatted = format_aspects(aspects)
            aspect_text = "\n".join(formatted) if formatted else "Нет значимых аспектов."
            days_data.append(f"=== {label} ===\nТранзиты:\n{transit_text}\nАспекты:\n{aspect_text}")

        client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        combined = "\n\n".join(days_data)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": build_system_prompt()},
                {"role": "user", "content": f"Составь прогноз на каждый из 7 дней. Для каждого дня — отдельный абзац с датой. Только значимые транзиты. Психологический и событийный уровень. Без клише и воды.\n\n{combined}"},
            ],
            temperature=0.7,
            max_tokens=2500,
        )
        text = response.choices[0].message.content
        full = "📆 Прогноз на неделю\n\n" + text
        for chunk in send_chunks(full, query.message.chat_id, None):
            await context.bot.send_message(chat_id=query.message.chat_id, text=chunk)

    elif query.data == "month":
        await query.edit_message_text("Строю прогноз на месяц (одну минуту)...")
        days_data = []
        for i in [0, 7, 14, 21, 28]:
            day = now_utc + timedelta(days=i)
            transits = get_transit_positions(day)
            aspects = find_aspects(transits)
            label = (datetime.now(msk) + timedelta(days=i)).strftime("%d.%m")
            transit_text = "\n".join(
                f"{n}: {d['sign']} {d['deg']}°{'[Ретро]' if d['retro'] else ''}"
                for n, d in transits.items()
            )
            formatted = format_aspects(aspects)
            aspect_text = "\n".join(formatted) if formatted else "Нет значимых аспектов."
            days_data.append(f"=== {label} ===\nТранзиты:\n{transit_text}\nАспекты:\n{aspect_text}")

        client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        combined = "\n\n".join(days_data)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": build_system_prompt()},
                {"role": "user", "content": f"Составь прогноз на месяц по ключевым неделям. Для каждой недели — абзац. Акцент на медленных транзитах и трендах. Психологический и событийный уровень.\n\n{combined}"},
            ],
            temperature=0.7,
            max_tokens=2500,
        )
        text = response.choices[0].message.content
        full = "🗓 Прогноз на месяц\n\n" + text
        for chunk in send_chunks(full, query.message.chat_id, None):
            await context.bot.send_message(chat_id=query.message.chat_id, text=chunk)

    elif query.data == "year":
        await query.edit_message_text("Строю годовой прогноз (2-3 минуты)...")
        days_data = []
        for m in range(1, 13):
            try:
                day = now_utc.replace(month=m, day=1)
                if day < now_utc:
                    day = day.replace(year=now_utc.year + 1)
            except ValueError:
                continue
            transits = get_transit_positions(day)
            aspects = find_aspects(transits)
            label = day.strftime("%B %Y")
            transit_text = "\n".join(
                f"{n}: {d['sign']} {d['deg']}°{'[Ретро]' if d['retro'] else ''}"
                for n, d in transits.items()
            )
            formatted = format_aspects(aspects)
            aspect_text = "\n".join(formatted) if formatted else "Нет значимых аспектов."
            days_data.append(f"=== {label} ===\nТранзиты:\n{transit_text}\nАспекты:\n{aspect_text}")

        client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        combined = "\n\n".join(days_data)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": build_system_prompt()},
                {"role": "user", "content": f"Составь годовой прогноз по месяцам. Акцент на медленных транзитах — Сатурн, Уран, Нептун, Плутон. Тренды и ключевые периоды. Для каждого месяца — короткий абзац.\n\n{combined}"},
            ],
            temperature=0.7,
            max_tokens=3000,
        )
        text = response.choices[0].message.content
        full = "📊 Прогноз на год\n\n" + text
        for chunk in send_chunks(full, query.message.chat_id, None):
            await context.bot.send_message(chat_id=query.message.chat_id, text=chunk)

    elif query.data == "custom_date":
        await query.edit_message_text(
            "Напиши дату в формате ДД.ММ.ГГГГ или период ДД.ММ.ГГГГ-ДД.ММ.ГГГГ\n\nНапример: 17.08.2026"
        )
        context.user_data["waiting_for_date"] = True

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text

    # Обработка пользовательской даты
    if context.user_data.get("waiting_for_date"):
        context.user_data["waiting_for_date"] = False
        msk = pytz.timezone("Europe/Moscow")
        try:
            if "-" in user_text and user_text.count(".") >= 4:
                # период
                parts = user_text.split("-")
                date_from = datetime.strptime(parts[0].strip(), "%d.%m.%Y")
                date_to = datetime.strptime(parts[1].strip(), "%d.%m.%Y")
                days_data = []
                current = date_from
                step = max(1, (date_to - date_from).days // 5)
                while current <= date_to:
                    dt_utc = current.replace(tzinfo=pytz.utc)
                    transits = get_transit_positions(dt_utc)
                    aspects = find_aspects(transits)
                    label = current.strftime("%d.%m")
                    transit_text = "\n".join(f"{n}: {d['sign']} {d['deg']}°" for n, d in transits.items())
                    formatted = format_aspects(aspects)
                    aspect_text = "\n".join(formatted) if formatted else "Нет значимых аспектов."
                    days_data.append(f"=== {label} ===\n{transit_text}\n{aspect_text}")
                    current += timedelta(days=step)
                client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
                combined = "\n\n".join(days_data)
                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": build_system_prompt()},
                        {"role": "user", "content": f"Прогноз на период {user_text}. Ключевые тренды и события.\n\n{combined}"},
                    ],
                    temperature=0.7, max_tokens=2000,
                )
                text = response.choices[0].message.content
                full = f"📌 Период {user_text}\n\n{text}"
            else:
                # один день
                target = datetime.strptime(user_text.strip(), "%d.%m.%Y")
                dt_utc = target.replace(tzinfo=pytz.utc)
                transits = get_transit_positions(dt_utc)
                aspects = find_aspects(transits)
                text = generate_forecast(user_text.strip(), transits, aspects)
                full = f"📌 {user_text}\n\n{text}"

            for chunk in send_chunks(full, update.message.chat_id, None):
                await update.message.reply_text(chunk)
            return
        except ValueError:
            await update.message.reply_text("Не смогла распознать дату. Попробуй формат ДД.ММ.ГГГГ")
            return

    # Обычный разговорный режим
    conversation_history.append({"role": "user", "content": user_text})
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    now_utc = datetime.utcnow()
    transits = get_transit_positions(now_utc)
    transit_text = "\n".join(
        f"{n}: {d['sign']} {d['deg']}°{'[Ретро]' if d['retro'] else ''}"
        for n, d in transits.items()
    )
    messages = [{"role": "system", "content": build_system_prompt()}] + conversation_history[-10:]
    messages[-1] = dict(messages[-1])
    messages[-1]["content"] += f"\n\n[Текущие транзиты:\n{transit_text}]"
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        temperature=0.7,
        max_tokens=1000,
    )
    reply = response.choices[0].message.content
    conversation_history.append({"role": "assistant", "content": reply})
    for chunk in send_chunks(reply, update.message.chat_id, None):
        await update.message.reply_text(chunk)

# ─── FLASK ─────────────────────────────────────────────────────────
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "Astro Agent is running."

def keep_alive():
    url = os.environ.get("RENDER_URL", "")
    if url:
        try:
            requests.get(url, timeout=10)
        except Exception:
            pass

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)

async def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(send_daily_forecast, "cron", hour=8, minute=0,
                      kwargs={"bot": app.bot})
    scheduler.add_job(keep_alive, "interval", minutes=10)
    scheduler.start()

    threading.Thread(target=run_flask, daemon=True).start()

    async with app:
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
