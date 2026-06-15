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
                    hits.append(
                        f"транзитный {t_name} {asp_name} натальный {n_name} "
                        f"(орб {exact}°, {t_data['sign']} {t_data['deg']}°)"
                    )
    return hits

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
    return f"""Ты — опытный астролог-практик, работающий в традиции эллинистической и средневековой астрологии.
Твой клиент — Олли, женщина.

{natal}

Правила составления прогноза:
1. Никаких клише ("звёзды благоволят", "будь осторожен"). Только конкретика.
2. Каждое утверждение — астрологический аргумент: какой транзит, к какой точке, орб.
3. Учитывай эссенциальные и акцидентальные достоинства планет.
4. Упоминай ретроградность если есть.
5. Говори о реальных темах домов конкретно для этого человека.
6. Значимые транзиты (орб до 1°) — выдели как ключевые.
7. Живой язык, на "ты", без пафоса.
8. Структура дня: общий тон → ключевые транзиты → на что обратить внимание → чего не делать."""

def generate_forecast(period_label, transits, aspects):
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    transit_text = "\n".join(
        f"{n}: {d['sign']} {d['deg']}°{'[Ретро]' if d['retro'] else ''}"
        for n, d in transits.items()
    )
    aspect_text = "\n".join(aspects) if aspects else "Значимых аспектов нет."
    user_msg = f"""Составь прогноз на {period_label}.

Транзитные планеты:
{transit_text}

Активные аспекты к натальной карте:
{aspect_text}

Дай развёрнутый конкретный прогноз."""

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
    await bot.send_message(chat_id=CHAT_ID, text=f"🌙 Прогноз на {today_str}\n\n{text}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📅 Прогноз на сегодня", callback_data="today")],
        [InlineKeyboardButton("📆 На неделю", callback_data="week"),
         InlineKeyboardButton("🗓 На месяц", callback_data="month")],
        [InlineKeyboardButton("📊 На год", callback_data="year")],
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
        await context.bot.send_message(chat_id=query.message.chat_id,
                                       text=f"📅 {label}\n\n{text}")

    elif query.data == "week":
        await query.edit_message_text("Строю прогноз на неделю...")
        now_utc = datetime.utcnow()
        msk = pytz.timezone("Europe/Moscow")
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
            aspect_text = "\n".join(aspects) if aspects else "Нет значимых аспектов."
            days_data.append(f"=== {label} ===\nТранзиты:\n{transit_text}\nАспекты:\n{aspect_text}")

        client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        combined = "\n\n".join(days_data)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": build_system_prompt()},
                {"role": "user", "content": f"Составь прогноз на каждый из 7 дней. Для каждого дня — отдельный абзац с датой, ключевыми транзитами и конкретными рекомендациями. Без клише.\n\n{combined}"},
            ],
            temperature=0.7,
            max_tokens=2000,
        )
        text = response.choices[0].message.content
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="📆 Прогноз на неделю\n\n" + text
        )

    elif query.data == "month":
        await query.edit_message_text("Строю прогноз на месяц (займёт минуту)...")
        forecasts = []
        for i in [1, 5, 10, 15, 20, 25, 30]:
            day = now_utc + timedelta(days=i)
            transits = get_transit_positions(day)
            aspects = find_aspects(transits)
            label = (datetime.now(msk) + timedelta(days=i)).strftime("%d.%m")
            forecasts.append(f"── {label} ──\n{generate_forecast(label, transits, aspects)}")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="🗓 Ключевые дни месяца\n\n" + "\n\n".join(forecasts)
        )

    elif query.data == "year":
        await query.edit_message_text("Строю годовой прогноз...")
        forecasts = []
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
            forecasts.append(f"── {label} ──\n{generate_forecast(label, transits, aspects)}")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="📊 Прогноз на год\n\n" + "\n\n".join(forecasts)
        )

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
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
    await update.message.reply_text(reply)

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

# ─── MAIN ──────────────────────────────────────────────────────────
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
