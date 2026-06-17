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

# Орбисы по планетам
ORB_TABLE = {
    "Солнце":   {"соединение": 7, "оппозиция": 5, "трин": 5, "квадрат": 4, "секстиль": 4},
    "Луна":     {"соединение": 7, "оппозиция": 5, "трин": 5, "квадрат": 4, "секстиль": 4},
    "Меркурий": {"соединение": 5, "оппозиция": 3, "трин": 3, "квадрат": 2, "секстиль": 2},
    "Венера":   {"соединение": 5, "оппозиция": 3, "трин": 3, "квадрат": 2, "секстиль": 2},
    "Марс":     {"соединение": 5, "оппозиция": 3, "трин": 3, "квадрат": 2, "секстиль": 2},
    "Юпитер":   {"соединение": 3, "оппозиция": 2, "трин": 2, "квадрат": 1, "секстиль": 1},
    "Сатурн":   {"соединение": 3, "оппозиция": 2, "трин": 2, "квадрат": 1, "секстиль": 1},
    "Уран":     {"соединение": 1.5, "оппозиция": 1, "трин": 1, "квадрат": 0.5, "секстиль": 0.5},
    "Нептун":   {"соединение": 1.5, "оппозиция": 1, "трин": 1, "квадрат": 0.5, "секстиль": 0.5},
    "Плутон":   {"соединение": 1.5, "оппозиция": 1, "трин": 1, "квадрат": 0.5, "секстиль": 0.5},
    "Сев.Узел": {"соединение": 1, "оппозиция": 99, "трин": 99, "квадрат": 99, "секстиль": 99},
    "Лилит":    {"соединение": 1, "оппозиция": 99, "трин": 99, "квадрат": 99, "секстиль": 99},
    "Хирон":    {"соединение": 1, "оппозиция": 99, "трин": 99, "квадрат": 99, "секстиль": 99},
    "Фортуна":  {"соединение": 1, "оппозиция": 99, "трин": 99, "квадрат": 99, "секстиль": 99},
}

ASPECTS = {
    "соединение": 0, "оппозиция": 180, "трин": 120, "квадрат": 90, "секстиль": 60,
}

PRIORITY = {
    "Уран": 1, "Нептун": 1, "Плутон": 1,
    "Юпитер": 2, "Сатурн": 2,
    "Марс": 3,
    "Солнце": 4, "Меркурий": 4, "Венера": 4, "Луна": 4, "Сев.Узел": 4,
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
    for t_name, t_data in transits.items():
        orb_rules = ORB_TABLE.get(t_name, {"соединение": 2, "оппозиция": 2, "трин": 2, "квадрат": 2, "секстиль": 2})
        for n_name, n_data in NATAL["planets_natal"].items():
            diff = abs(t_data["deg_abs"] - n_data["deg"]) % 360
            if diff > 180:
                diff = 360 - diff
            for asp_name, asp_deg in ASPECTS.items():
                orb_allowed = orb_rules.get(asp_name, 2)
                exact = abs(diff - asp_deg)
                if exact <= orb_allowed:
                    direction = "сход." if t_data["deg_abs"] < n_data["deg"] else "расход."
                    fast_to_slow = (t_name in ["Луна", "Меркурий", "Венера", "Солнце"]
                                    and n_name in ["Сатурн", "Уран", "Нептун", "Плутон"])
                    hits.append({
                        "t_name": t_name,
                        "n_name": n_name,
                        "asp_name": asp_name,
                        "orb": round(exact, 2),
                        "direction": direction,
                        "fast_to_slow": fast_to_slow,
                        "priority": PRIORITY.get(t_name, 5),
                        "retro": t_data["retro"],
                    })
    hits.sort(key=lambda x: (x["priority"], x["orb"]))
    return hits

def format_aspects_for_prompt(hits):
    lines = []
    for h in hits:
        retro = " ℞" if h["retro"] else ""
        note = ""
        if h["direction"] == "расход." and h["orb"] > 1.5:
            note = " [расход. >1.5° — не описывать]"
        if h["fast_to_slow"]:
            note += " [быстрая по медленной — фон]"
        lines.append(
            f"{'🔴' if h['priority']==1 else '🟡' if h['priority']==2 else '🟠' if h['priority']==3 else '⚪'} "
            f"{h['t_name']}{retro} {h['asp_name']} натальный {h['n_name']} {h['orb']}° ({h['direction']}){note}"
        )
    return lines

def build_natal_summary():
    lines = ["Натальная карта: Олли, 17.11.1990, 13:20, Астрахань",
             "ASC Рыбы 8°58, MC Стрелец 20°08", ""]
    for p, d in NATAL["planets_natal"].items():
        r = " [ретро]" if "ретро" in d.get("status", "") else ""
        lines.append(f"{p}: {d['sign']} {d['deg']}°, дом {d['house']}{r} ({d['status']})")
    lines += ["", "Натальные аспекты:"] + NATAL["aspects_natal"]
    lines += ["", "Особенности:", NATAL["special"]]
    return "\n".join(lines)

def build_system_prompt(mode="full"):
    natal = build_natal_summary()

    mode_instruction = ""
    if mode == "intro":
        mode_instruction = "\n\n⚠️ РЕЖИМ: Сейчас составляй ТОЛЬКО приветствие, список транзитов и общую картину дня (пункты 1-2-3 из структуры). НЕ пиши блоки сфер и Луну без курса — это будет отдельным запросом."
    elif mode == "spheres":
        mode_instruction = "\n\n⚠️ РЕЖИМ: Сейчас составляй ТОЛЬКО блок СФЕР (пункт 4) и Луну без курса если есть (пункт 5). НЕ пиши приветствие, список транзитов и общую картину — это уже отправлено отдельно. Начни прямо с 💕 Отношения."

    return f"""Ты — личный астролог Оли. Общаешься как близкая подруга которая профессионально знает астрологию. Никакого официоза, никаких умных слов ради умных слов. Язык простой, живой, тёплый. Смайлики везде — щедро.

═══ НАТАЛЬНАЯ КАРТА ═══

{natal}

═══ КАРТА ДОМОВ ═══

Дом 1 (Рыбы 8°58): Фортуна | упр. Нептун в 11 доме
Дом 2 (Овен 29°21 → тело в Тельце): пусто | упр. Марс в 3 доме ретро
  ⚠️ Куспид в последнем градусе Овна — финансы через Овен И через Телец
Дом 3 (Телец 28°56 → тело в Близнецах): Марс ретро | упр. Венера в 8 доме
  ⚠️ Куспид в последнем градусе Тельца — коммуникации через Телец И через Близнецы
Дом 4 (Близнецы 20°08): пусто | упр. Меркурий в 9 доме
Дом 5 (Рак 9°34): Хирон ретро, Южный узел | упр. Луна в 8 доме
Дом 6 (Лев 2°21): Юпитер | упр. Солнце в 8 доме
Дом 7 (Дева 8°58): пусто | упр. Меркурий в 9 доме
Дом 8 (Весы 29°21 → тело в Скорпионе): Солнце, Луна, Венера, Плутон | упр. Венера в 8 доме
  ⚠️ Куспид Весы но планеты в Скорпионе — читать через оба знака: Весы (баланс, партнёрство) + Скорпион (глубина, трансформация, тайное)
Дом 9 (Скорпион 28°56 → тело в Стрельце): Меркурий, Лилит | упр. Марс в 3 доме ретро
  ⚠️ Темы 9 дома через оба знака: Скорпион (глубина убеждений) + Стрелец (путешествия, философия)
Дом 10 (Стрелец 20°08): Уран | упр. Юпитер в 6 доме
Дом 11 (Козерог 9°34): Сатурн, Нептун, Северный узел | упр. Сатурн в 11 доме (обитель)
Дом 12 (Водолей 2°21): пусто | упр. Сатурн в 11 доме

═══ СФЕРЫ ЖИЗНИ ═══

💕 Отношения → дома 7, 5, 8, 3, 4, 9
— 7 дом (Дева, пустой): муж, близкие друзья, партнёры по бизнесу, открытые враги
— 5 дом (Рак, Хирон ретро + Южный узел): романтика, флирт, азарт, творчество. Южный узел — тема удачи из прошлого, Хирон — уязвимость в романтике
— 8 дом (Весы→Скорпион, Солнце+Луна+Венера+Плутон): интимная жизнь, глубокое слияние, трансформация через партнёра
— 3 дом (Телец→Близнецы, Марс ретро): братья/сёстры, дальние родственники, соседи
— 4 дом (Близнецы, пустой): родители, дом, семейные корни
— 9 дом (Скорпион→Стрелец, Меркурий+Лилит): свёкор/свекровь, родители партнёра

💼 Работа/проекты/карьера → дома 10, 6, 2
— 10 дом (Стрелец, Уран): карьера, самореализация, репутация, публичность. Уран — нестандартный путь
— 6 дом (Лев, Юпитер): ежедневная работа, рутина, коллеги, подчинённые. Юпитер — расширение через труд
— 2 дом (Овен→Телец, пустой): доход от профессии, заработок навыками

💚 Здоровье → дома 6, 1, 8, 12
— 6 дом (Лев, Юпитер): непосредственное здоровье, режим. Юпитер — склонность к избытку
— 1 дом (Рыбы, Фортуна): тело, физическое состояние. Фортуна на Асценденте — сильная точка удачи
— 8 дом (Весы→Скорпион): неожиданные болезни, травмы, хирургия, регенерация
— 12 дом (Водолей, пустой): скрытые болезни, психосоматика, госпитализации

💰 Финансы → дома 2, 8, 11, 5
— 2 дом (Овен→Телец, пустой): личные финансы, доходы, расходы
— 8 дом (Весы→Скорпион): чужие деньги — мужа, родственников, банки, кредиты, наследство
— 11 дом (Козерог, Сатурн+Нептун): финансовая помощь от друзей/сообщества. Сатурн — дисциплина, Нептун — риск иллюзий
— 5 дом (Рак, Хирон+Южный узел): азарт, лотереи, спекуляции. Южный узел — осторожно с риском

═══ ОРБИСЫ ДЛЯ ТРАНЗИТОВ ═══

Солнце, Луна: соединение 7°, трин/оппозиция 5°, квадрат/секстиль 4°
Меркурий, Венера, Марс: соединение 5°, трин/оппозиция 3°, квадрат/секстиль 2°
Юпитер, Сатурн: соединение 3°, трин/оппозиция 2°, квадрат/секстиль 1°
Уран, Нептун, Плутон: соединение 1.5°, трин/оппозиция 1°, квадрат/секстиль 0.5°
Фиктивные точки: только соединение орб до 1°
Расходящийся орб >1.5° — в список включать, в описание НЕ включать

═══ СТРУКТУРА ПРОГНОЗА НА ДЕНЬ ═══

1. ПРИВЕТСТВИЕ
Короткое, с датой. Чередуй обращения: Оля, Олюшка, Олечка, Оль. Смайлики щедро.

2. СПИСОК ВСЕХ АКТИВНЫХ ТРАНЗИТОВ
Полный список ВСЕХ транзитов в рамках орбисов — даже незначительных.
Формат каждой строки: [эмодзи приоритета] Планета аспект натальная_Планета X.XX° (сход./расход.)
🔴 Уран, Нептун, Плутон | 🟡 Юпитер, Сатурн | 🟠 Марс | ⚪ быстрые
Внутри группы — по орбу от меньшего к большему.
Если планета ретро — добавь ℞ после названия.

Отдельно под списком — если планета вошла в новый дом сегодня:
🏠 [Планета] входит в [N] дом — [краткое название периода]

3. ОБЩАЯ КАРТИНА ДНЯ
7-16 фраз в зависимости от насыщенности.
Объединяй транзиты в общий смысл — НЕ разбирай каждый по отдельности.
Пиши образно и живо: "у тебя сейчас...", "может случиться...", "самое время...".
Соединяй психологический и событийный уровень в одном тексте.
Конкретика: не "плохое настроение" а "можешь сорваться на близких без причины".
Луна по домам — коротко как текстура дня: "Луна в твоём 3 доме — день суетливый, много мелких дел".

ПРАВИЛО ТРЕНДОВ (обязательно):
— Медленный транзит только что вошёл в орб → упомяни что это тренд на недели/месяцы
— Транзит идёт уже давно → НЕ повторяй каждый день. Упомяни только если:
  а) к нему присоединилась ещё одна планета
  б) он достиг точности орб до 0.3°
  в) другая планета активирует ту же натальную точку
— После точности расходящийся → только в список, в текст НЕ включать

ПРОХОДЫ ПЛАНЕТ ЧЕРЕЗ КУСПИДЫ ДОМОВ:
— Луна → коротко, фон дня
— Марс, Венера, Меркурий, Солнце → абзац про ближайшие недели
— Юпитер, Сатурн → отдельный акцент, период на месяцы
— Уран, Нептун, Плутон → важное событие, период на годы

4. СФЕРЫ — писать ВСЕ ЧЕТЫРЕ всегда
Если нет значимых транзитов по сфере — короткая фраза о фоне.
Если есть — 7-10 предложений. Описывай что это значит для жизни, НЕ описывай транзит.
Учитывай двойные знаки в домах 2, 3, 8, 9 при интерпретации.

ЗАПРЕЩЕНО В ИНТЕРПРЕТАЦИИ (и в общей картине дня, и в сферах):
— Названия аспектов (трин, квадрат, секстиль, оппозиция, соединение)
— Градусы и орбы (0.13°, 1.46° и т.п.)
— Технические упоминания типа "Сатурн трин Юпитеру"
Список транзитов уже есть выше отдельным блоком — там вся техническая информация.
В тексте интерпретации — только смысл и суть, без повторения технических деталей.
Плохо: "Сатурн трин Юпитеру (0.13°) может указывать на дисциплину"
Хорошо: "сейчас у тебя период стабильного роста — самое время довести начатое до конца"

5. ЛУНА БЕЗ КУРСА
Если Луна сейчас без курса — напиши блок:
🌙 Луна без курса с ЧЧ:ММ до ЧЧ:ММ МСК — лучше не начинать новых дел, не подписывать договоры, не делать важных покупок.
Если Луна НЕ без курса — НЕ пиши про это вообще ничего, ни слова, пропусти этот пункт полностью.

═══ СТРУКТУРА ПРОГНОЗА НА НЕДЕЛЮ ═══

1. ПРИВЕТСТВИЕ с датами периода. Смайлики.
2. КРАТКИЙ ОБЗОР НЕДЕЛИ — 3-5 фраз. Общее настроение, доминирующие тренды.
3. ПО ДНЯМ — для каждого дня с датой:
— Дата и день недели
— 2-4 фразы: что важного, если есть значимые транзиты — упомяни. Если день тихий — так и скажи.
— Луна в каком доме — одна фраза о текстуре дня.
4. БЛОК СФЕР ЗА НЕДЕЛЮ (в конце, один раз):
Для каждой сферы — что важного происходит за всю неделю, ключевые даты.
💕 Отношения | 💼 Работа | 💚 Здоровье | 💰 Финансы

═══ СТРУКТУРА ПРОГНОЗА НА МЕСЯЦ ═══

1. ПРИВЕТСТВИЕ с названием месяца. Смайлики.
2. КРАТКИЙ ОБЗОР МЕСЯЦА — 4-6 фраз. Главные тренды, доминирующие транзиты.
3. ПО НЕДЕЛЯМ:
— Неделя N (даты)
— Общий обзор недели 3-4 фразы
— Значимые события с датами если есть
4. БЛОК СФЕР ЗА МЕСЯЦ (в конце, один раз):
Для каждой сферы — тренды и ключевые даты за весь месяц.
💕 Отношения | 💼 Работа | 💚 Здоровье | 💰 Финансы

═══ СТРУКТУРА ПРОГНОЗА НА ГОД ═══

1. ПРИВЕТСТВИЕ с периодом (12 месяцев от даты запроса). Смайлики.
2. ОБЩИЕ ТЕНДЕНЦИИ ГОДА — 5-7 фраз. Главные медленные транзиты, глобальные темы.
3. ПО МЕСЯЦАМ — для каждого месяца:
— Название месяца
— 3-5 фраз: общее настроение, значимые события с датами
4. БЛОК СФЕР ЗА ГОД (в конце, один раз):
Для каждой сферы — тренды, благоприятные и сложные периоды, ключевые даты.
💕 Отношения | 💼 Работа | 💚 Здоровье | 💰 Финансы

═══ СТРУКТУРА ПРОГНОЗА НА ПЕРИОД ═══

Если период 1-3 дня → прогноз как на день (та же структура).
Если период 4+ дней → обзор:
1. Приветствие с датами периода.
2. Общий обзор периода 3-5 фраз.
3. Значимые даты и события внутри периода.
4. Блок сфер за период (в конце, один раз).

═══ ЖЁСТКИЕ ПРАВИЛА ═══

ПРИОРИТЕТЫ: Уран/Нептун/Плутон > Юпитер/Сатурн > Марс > быстрые
Сходящийся важнее расходящегося. Расходящийся орб >1.5° — в список, в текст НЕТ.
Транзит быстрой по медленной натальной — незначительный фон, в описание не включать.

ДВОЙНЫЕ ЗНАКИ: дома 2, 3, 8, 9 — учитывай оба знака при интерпретации всегда.

ГАЛЛЮЦИНАЦИИ ЗАПРЕЩЕНЫ:
— Никогда не придумывать транзиты которых нет в переданных данных
— Транзитная Луна к натальной Луне ≠ Луна без курса — это разные вещи
— Если данных не хватает — скажи прямо

РАЗГОВОРНЫЙ РЕЖИМ:
— Вопрос после прогноза → отвечай по существу, не повторяй прогноз
— Вопрос про тему → анализируй только соответствующие дома
— Вопрос про дату → опирайся только на переданные данные, не додумывай
— Вопрос про транзит к конкретной планете → только переданные данные

ЗАПРЕЩЁННЫЕ ФРАЗЫ:
"звёзды благоволят", "будь осторожна", "прекрасное время для", "доверяй себе",
"слушай интуицию", "энергия дня", "Вселенная посылает", "всё будет хорошо",
"планеты говорят", "небо сулит", "Космос направляет"
ПИШИ НА ЧИСТОМ РУССКОМ ЯЗЫКЕ. Никогда не вставляй иероглифы, китайские или другие нелатинские/нерусские символы — если не уверена в слове, используй простой синоним.
{mode_instruction}
"""

def generate_forecast(period_label, transits, aspects_raw):
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    transit_text = "\n".join(
        f"{n}: {d['sign']} {d['deg']}°{'[Ретро]' if d['retro'] else ''}"
        for n, d in transits.items()
    )
    formatted = format_aspects_for_prompt(aspects_raw)
    aspect_text = "\n".join(formatted) if formatted else "Значимых аспектов нет."

    base_data = f"""Дата прогноза: {period_label}

Транзитные планеты:
{transit_text}

Активные аспекты (отсортированы по приоритету и орбу — используй ТОЛЬКО эти данные, ничего не придумывай):
{aspect_text}"""

    intro_response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": build_system_prompt(mode="intro")},
            {"role": "user", "content": f"{base_data}\n\nСоставь приветствие, полный список транзитов и общую картину дня. Используй ТОЛЬКО переданные аспекты, не добавляй других."},
        ],
        temperature=0.6,
        max_tokens=1200,
    )
    intro_text = intro_response.choices[0].message.content

    spheres_response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": build_system_prompt(mode="spheres")},
            {"role": "user", "content": f"{base_data}\n\nСоставь блок СФЕР (Отношения/Работа/Здоровье/Финансы) и Луну без курса если применимо. Для каждой сферы используй ТОЛЬКО те аспекты из списка выше, которые касаются домов этой сферы. Если для сферы нет релевантных аспектов — напиши короткую фразу о фоне, не повторяй один и тот же текст для разных сфер."},
        ],
        temperature=0.6,
        max_tokens=1500,
    )
    spheres_text = spheres_response.choices[0].message.content

    return f"{intro_text}\n\n{spheres_text}"

def send_chunks(text, chat_id=None, bot_send_func=None):
    chunk_size = 3800
    return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]

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
    for chunk in send_chunks(full):
        await bot.send_message(chat_id=CHAT_ID, text=chunk)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📅 Сегодня", callback_data="today"),
         InlineKeyboardButton("📅 Завтра", callback_data="tomorrow")],
        [InlineKeyboardButton("📆 Неделя", callback_data="week"),
         InlineKeyboardButton("🗓 Месяц", callback_data="month")],
        [InlineKeyboardButton("📊 Год", callback_data="year"),
         InlineKeyboardButton("📌 Дата/период", callback_data="custom_date")],
    ]
    await update.message.reply_text(
        "Привет, Олюшка! 🌙 Я твой личный астролог.\n\nЧто хочешь узнать?",
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
        await query.edit_message_text("✨ Считаю транзиты...")
        text = generate_forecast(label, transits, aspects)
        full = f"📅 {label}\n\n{text}"
        for chunk in send_chunks(full):
            await context.bot.send_message(chat_id=query.message.chat_id, text=chunk)

    elif query.data == "tomorrow":
        day = now_utc + timedelta(days=1)
        transits = get_transit_positions(day)
        aspects = find_aspects(transits)
        label = (datetime.now(msk) + timedelta(days=1)).strftime("%d.%m.%Y")
        await query.edit_message_text("✨ Считаю транзиты...")
        text = generate_forecast(label, transits, aspects)
        full = f"📅 Завтра {label}\n\n{text}"
        for chunk in send_chunks(full):
            await context.bot.send_message(chat_id=query.message.chat_id, text=chunk)

    elif query.data == "week":
        await query.edit_message_text("📆 Строю прогноз на неделю...")
        days_data = []
        for i in range(7):
            day = now_utc + timedelta(days=i)
            transits = get_transit_positions(day)
            aspects = find_aspects(transits)
            label = (datetime.now(msk) + timedelta(days=i)).strftime("%d.%m (%A)")
            transit_text = "\n".join(
                f"{n}: {d['sign']} {d['deg']}°{'[Ретро]' if d['retro'] else ''}"
                for n, d in transits.items()
            )
            formatted = format_aspects_for_prompt(aspects)
            aspect_text = "\n".join(formatted) if formatted else "Нет значимых аспектов."
            days_data.append(f"=== {label} ===\nТранзиты:\n{transit_text}\nАспекты:\n{aspect_text}")

        client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        combined = "\n\n".join(days_data)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": build_system_prompt()},
                {"role": "user", "content": f"Составь прогноз на неделю. Используй структуру ПРОГНОЗА НА НЕДЕЛЮ из инструкций. Блок сфер — в конце один раз за всю неделю с ключевыми датами.\n\n{combined}"},
            ],
            temperature=0.7,
            max_tokens=3000,
        )
        text = response.choices[0].message.content
        full = "📆 Прогноз на неделю\n\n" + text
        for chunk in send_chunks(full):
            await context.bot.send_message(chat_id=query.message.chat_id, text=chunk)

    elif query.data == "month":
        await query.edit_message_text("🗓 Строю прогноз на месяц (одну минуту)...")
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
            formatted = format_aspects_for_prompt(aspects)
            aspect_text = "\n".join(formatted) if formatted else "Нет значимых аспектов."
            days_data.append(f"=== Неделя от {label} ===\nТранзиты:\n{transit_text}\nАспекты:\n{aspect_text}")

        client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        combined = "\n\n".join(days_data)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": build_system_prompt()},
                {"role": "user", "content": f"Составь прогноз на месяц. Используй структуру ПРОГНОЗА НА МЕСЯЦ из инструкций. Блок сфер — в конце один раз за весь месяц с ключевыми датами.\n\n{combined}"},
            ],
            temperature=0.7,
            max_tokens=3000,
        )
        text = response.choices[0].message.content
        full = "🗓 Прогноз на месяц\n\n" + text
        for chunk in send_chunks(full):
            await context.bot.send_message(chat_id=query.message.chat_id, text=chunk)

    elif query.data == "year":
        await query.edit_message_text("📊 Строю годовой прогноз (2-3 минуты)...")
        days_data = []
        for m in range(12):
            day = now_utc + timedelta(days=m*30)
            transits = get_transit_positions(day)
            aspects = find_aspects(transits)
            label = day.strftime("%B %Y")
            transit_text = "\n".join(
                f"{n}: {d['sign']} {d['deg']}°{'[Ретро]' if d['retro'] else ''}"
                for n, d in transits.items()
            )
            formatted = format_aspects_for_prompt(aspects)
            aspect_text = "\n".join(formatted) if formatted else "Нет значимых аспектов."
            days_data.append(f"=== {label} ===\nТранзиты:\n{transit_text}\nАспекты:\n{aspect_text}")

        client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        combined = "\n\n".join(days_data)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": build_system_prompt()},
                {"role": "user", "content": f"Составь годовой прогноз на 12 месяцев вперёд. Используй структуру ПРОГНОЗА НА ГОД из инструкций. Блок сфер — в конце один раз за весь год с ключевыми периодами и датами.\n\n{combined}"},
            ],
            temperature=0.7,
            max_tokens=4000,
        )
        text = response.choices[0].message.content
        full = "📊 Прогноз на год\n\n" + text
        for chunk in send_chunks(full):
            await context.bot.send_message(chat_id=query.message.chat_id, text=chunk)

    elif query.data == "custom_date":
        await query.edit_message_text(
            "📌 Напиши дату или период:\n\n"
            "• Один день: 17.08.2026\n"
            "• Период: 10.09.2026-20.09.2026"
        )
        context.user_data["waiting_for_date"] = True

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text

    if context.user_data.get("waiting_for_date"):
        context.user_data["waiting_for_date"] = False
        msk = pytz.timezone("Europe/Moscow")
        try:
            if "-" in user_text and user_text.count(".") >= 4:
                parts = user_text.split("-")
                date_from = datetime.strptime(parts[0].strip(), "%d.%m.%Y")
                date_to = datetime.strptime(parts[1].strip(), "%d.%m.%Y")
                delta_days = (date_to - date_from).days

                if delta_days <= 3:
                    dt_utc = date_from.replace(tzinfo=pytz.utc)
                    transits = get_transit_positions(dt_utc)
                    aspects = find_aspects(transits)
                    text = generate_forecast(user_text.strip(), transits, aspects)
                    full = f"📌 {user_text}\n\n{text}"
                else:
                    days_data = []
                    step = max(1, delta_days // 6)
                    current = date_from
                    while current <= date_to:
                        dt_utc = current.replace(tzinfo=pytz.utc)
                        transits = get_transit_positions(dt_utc)
                        aspects = find_aspects(transits)
                        label = current.strftime("%d.%m")
                        transit_text = "\n".join(f"{n}: {d['sign']} {d['deg']}°" for n, d in transits.items())
                        formatted = format_aspects_for_prompt(aspects)
                        aspect_text = "\n".join(formatted) if formatted else "Нет значимых аспектов."
                        days_data.append(f"=== {label} ===\n{transit_text}\n{aspect_text}")
                        current += timedelta(days=step)

                    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
                    combined = "\n\n".join(days_data)
                    response = client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[
                            {"role": "system", "content": build_system_prompt()},
                            {"role": "user", "content": f"Составь прогноз на период {user_text}. Используй структуру ПРОГНОЗА НА ПЕРИОД из инструкций. Блок сфер — в конце.\n\n{combined}"},
                        ],
                        temperature=0.7, max_tokens=2500,
                    )
                    text = response.choices[0].message.content
                    full = f"📌 Период {user_text}\n\n{text}"
            else:
                target = datetime.strptime(user_text.strip(), "%d.%m.%Y")
                dt_utc = target.replace(tzinfo=pytz.utc)
                transits = get_transit_positions(dt_utc)
                aspects = find_aspects(transits)
                text = generate_forecast(user_text.strip(), transits, aspects)
                full = f"📌 {user_text}\n\n{text}"

            for chunk in send_chunks(full):
                await update.message.reply_text(chunk)
            return
        except ValueError:
            await update.message.reply_text("Не смогла распознать дату 🤔 Попробуй формат ДД.ММ.ГГГГ или ДД.ММ.ГГГГ-ДД.ММ.ГГГГ")
            return

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
    messages[-1]["content"] += f"\n\n[Текущие транзиты для контекста:\n{transit_text}]"
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        temperature=0.7,
        max_tokens=1200,
    )
    reply = response.choices[0].message.content
    conversation_history.append({"role": "assistant", "content": reply})
    for chunk in send_chunks(reply):
        await update.message.reply_text(chunk)

# ─── FLASK ─────────────────────────────────────────────────────────
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "Astro Agent is running. 🌙"

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
