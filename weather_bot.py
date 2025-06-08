import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import requests
import sqlite3
from datetime import datetime, time
import os
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import matplotlib.pyplot as plt
import io
import base64

# Налаштування планувальника
scheduler = BackgroundScheduler()
scheduler.start()

# Налаштування OpenWeatherMap API
API_KEY = os.getenv("OPENWEATHER_API_KEY", "your_openweather_api_key")
WEATHER_URL = "http://api.openweathermap.org/data/2.5/weather"
FORECAST_URL = "http://api.openweathermap.org/data/2.5/forecast"

# Ініціалізація бази даних SQLite
def init_db():
    conn = sqlite3.connect("/app/data/weather_bot.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS requests
                 (user_id INTEGER, city TEXT, request_type TEXT, timestamp TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS favorite_cities
                 (user_id INTEGER, city TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS notifications
                 (user_id INTEGER, notify_time TEXT, UNIQUE(user_id, notify_time))''')
    c.execute('''CREATE TABLE IF NOT EXISTS alerts
                 (user_id INTEGER, enabled INTEGER, UNIQUE(user_id))''')
    conn.commit()
    conn.close()

# Збереження запиту
def save_request(user_id, city, request_type):
    conn = sqlite3.connect("/app/data/weather_bot.db")
    c = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO requests (user_id, city, request_type, timestamp) VALUES (?, ?, ?, ?)",
              (user_id, city, request_type, timestamp))
    conn.commit()
    conn.close()

# Збереження улюбленого міста
def save_favorite_city(user_id, city):
    conn = sqlite3.connect("/app/data/weather_bot.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO favorite_cities (user_id, city) VALUES (?, ?)", (user_id, city))
    conn.commit()
    conn.close()

# Отримання улюблених міст
def get_favorite_cities(user_id):
    conn = sqlite3.connect("/app/data/weather_bot.db")
    c = conn.cursor()
    c.execute("SELECT city FROM favorite_cities WHERE user_id = ?", (user_id,))
    cities = [row[0] for row in c.fetchall()]
    conn.close()
    return cities

# Збереження часу оповіщень
def save_notification_time(user_id, notify_time):
    conn = sqlite3.connect("/app/data/weather_bot.db")
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO notifications (user_id, notify_time) VALUES (?, ?)",
              (user_id, notify_time))
    conn.commit()
    conn.close()

# Отримання часу оповіщень
def get_notification_times(user_id):
    conn = sqlite3.connect("/app/data/weather_bot.db")
    c = conn.cursor()
    c.execute("SELECT notify_time FROM notifications WHERE user_id = ?", (user_id,))
    times = [row[0] for row in c.fetchall()]
    conn.close()
    return times

# Видалення оповіщень
def delete_notifications(user_id):
    conn = sqlite3.connect("/app/data/weather_bot.db")
    c = conn.cursor()
    c.execute("DELETE FROM notifications WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

# Збереження налаштувань сповіщень про екстремальну погоду
def save_alert_setting(user_id, enabled):
    conn = sqlite3.connect("/app/data/weather_bot.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO alerts (user_id, enabled) VALUES (?, ?)", (user_id, enabled))
    conn.commit()
    conn.close()

# Отримання історії запитів
def get_history(user_id, limit=5):
    conn = sqlite3.connect("/app/data/weather_bot.db")
    c = conn.cursor()
    c.execute("SELECT city, request_type, timestamp FROM requests WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
              (user_id, limit))
    history = c.fetchall()
    conn.close()
    return history

# Отримання поточної погоди
def get_current_weather(city):
    try:
        params = {"q": city, "appid": API_KEY, "units": "metric", "lang": "uk"}
        response = requests.get(WEATHER_URL, params=params)
        response.raise_for_status()
        data = response.json()
        temp = data["main"]["temp"]
        temp_min = data["main"]["temp_min"]
        temp_max = data["main"]["temp_max"]
        humidity = data["main"]["humidity"]
        wind = data["wind"]["speed"]
        description = data["weather"][0]["description"]
        weather_emoji = get_weather_emoji(description)
        advice = get_weather_advice(description, temp, wind, humidity)
        tip = get_daily_tip(description, temp, wind)
        uv_index = 0
        uv_advice = "Недоступно"
        return (f"📍 Погода в {city} 🌟:\n"
                f"{weather_emoji} • {description.title()}\n"
                f"🌡️ • Температура: {temp:.2f}°C (мін: {temp_min:.2f}°C, макс: {temp_max:.2f}°C) {get_temp_emoji(temp)}\n"
                f"💧 • Вологість: {humidity}% 💦\n"
                f"💨 • Вітер: {wind} м/с {get_wind_emoji(wind)}\n"
                f"☀️ • UV-індекс: {uv_index:.1f} ({uv_advice})\n\n"
                f"{advice}\n{tip}")
    except requests.RequestException:
        return f"Не вдалося знайти погоду для {city}."

# Отримання прогнозу на 5 днів
def get_forecast(city):
    try:
        params = {"q": city, "appid": API_KEY, "units": "metric", "lang": "uk"}
        response = requests.get(FORECAST_URL, params=params)
        response.raise_for_status()
        data = response.json()
        forecast = []
        temps = []
        dates = []
        rainy_days = 0
        for item in data["list"][::8]:
            date = item["dt_txt"].split()[0]
            temp = item["main"]["temp"]
            temp_min = item["main"]["temp_min"]
            temp_max = item["main"]["temp_max"]
            humidity = item["main"]["humidity"]
            wind = item["wind"]["speed"]
            description = item["weather"][0]["description"]
            weather_emoji = get_weather_emoji(description)
            tip = get_daily_tip(description, temp, wind)
            if "дощ" in description.lower():
                rainy_days += 1
            forecast.append(
                f"📍 {date} 🗓️\n"
                f"{weather_emoji} • {description.title()}\n"
                f"🌡️ • Температура: {temp:.2f}°C (мін: {temp_min:.2f}°C, макс: {temp_max:.2f}°C) {get_temp_emoji(temp)}\n"
                f"💧 • Вологість: {humidity}% 💦\n"
                f"💨 • Вітер: {wind} м/с {get_wind_emoji(wind)}\n"
                f"💡 • Порада: {tip}\n"
            )
            temps.append(temp)
            dates.append(date[-5:])
        conclusion = f"Висновок для {city}: "
        if rainy_days > 0:
            conclusion += (f"Теплий тиждень, але чекай на {rainy_days} дощових днів 🌧️. "
                          f"Тримай парасольку напоготові! ☂️")
        else:
            conclusion += "Теплий і приємний тиждень! 🌞 Ідеально для прогулянок 🚶‍♀️ і активного відпочинку 🚴‍♀️."
        chart = get_temperature_chart(dates, temps, city)
        return (f"📅 Прогноз погоди на 5 днів у {city} 🌟:\n\n" + "\n".join(forecast) + f"\n{conclusion}", chart)
    except requests.RequestException:
        return (f"Не вдалося знайти прогноз для {city}.", None)

# Емодзі для погоди
def get_weather_emoji(description):
    description = description.lower()
    if "дощ" in description:
        return "🌦️"
    elif "хмар" in description:
        return "☁️"
    elif "ясно" in description or "чисте" in description:
        return "☀️"
    return "🌤️"

# Емодзі для температури
def get_temp_emoji(temp):
    if temp < 5:
        return "❄️"
    elif temp < 20:
        return "😎"
    return "🔥"

# Емодзі для вітру
def get_wind_emoji(wind):
    if wind > 10:
        return "🌪️"
    elif wind > 5:
        return "🌬️"
    return "🍃"

# Рекомендація одягу
def get_weather_advice(description, temp, wind, humidity):
    description = description.lower()
    if "дощ" in description:
        return "Візьміть парасолю та водонепроникний одяг ☂️"
    elif temp < 5 or wind > 10:
        return "Одягніть теплий одяг, шапку та рукавички 🧥🧤"
    elif temp > 25 and humidity < 50:
        return "Легкий одяг і сонцезахисний крем 😎🧴"
    return "Одягайтеся зручно 👕"

# Порада дня
def get_daily_tip(description, temp, wind):
    description = description.lower()
    if "дощ" in description or wind > 10:
        return "Залишайтеся вдома з книгою або фільмом 📚🎬"
    elif temp > 20 and "ясно" in description:
        return "Ідеально для пікніка або прогулянки в парку! 🧺🌳"
    elif temp < 5:
        return "Час для гарячого чаю та теплої ковдри ☕🛋️"
    return "Чудовий день для будь-яких планів! 😊"

# Графік температури
def get_temperature_chart(dates, temps, city):
    plt.figure(figsize=(8, 4))
    plt.plot(dates, temps, marker='o', color='#3498db', label=f'Температура в {city} (°C)')
    plt.fill_between(dates, temps, color='rgba(52, 152, 219, 0.2)')
    plt.title(f'Прогноз температури в {city}')
    plt.xlabel('Дата')
    plt.ylabel('Температура (°C)')
    plt.legend()
    plt.grid(True)
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    plt.close()
    
    img_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    return img_base64

# Налаштування оповіщень
async def send_notification(context: ContextTypes.DEFAULT_TYPE, user_id, bot):
    cities = get_favorite_cities(user_id)
    if not cities:
        await bot.send_message(user_id, "Додайте улюблені міста через 'додати <місто>'.")
        return
    for city in cities:
        weather = get_current_weather(city)
        await bot.send_message(user_id, weather)

# Перевірка екстремальної погоди
async def check_extreme_weather(context: ContextTypes.DEFAULT_TYPE, user_id, bot):
    conn = sqlite3.connect("/app/data/weather_bot.db")
    c = conn.cursor()
    c.execute("SELECT enabled FROM alerts WHERE user_id = ?", (user_id,))
    enabled = c.fetchone()
    if not enabled or not enabled[0]:
        return
    cities = get_favorite_cities(user_id)
    for city in cities:
        params = {"q": city, "appid": API_KEY, "units": "metric", "lang": "uk"}
        try:
            response = requests.get(WEATHER_URL, params=params)
            response.raise_for_status()
            data = response.json()
            temp = data["main"]["temp"]
            description = data["weather"][0]["description"].lower()
            if temp > 30 or temp < -10 or "сильний дощ" in description or "шторм" in description:
                await bot.send_message(user_id, f"⚠️ Увага! Екстремальна погода в {city}: {temp}°C, {description}.")
        except requests.RequestException:
            pass

# Клавіатура для вибору типу прогнозу
def get_weather_keyboard():
    keyboard = [
        [InlineKeyboardButton("Погода зараз", callback_data="current")],
        [InlineKeyboardButton("Прогноз на 5 днів", callback_data="forecast")],
        [InlineKeyboardButton("Назад", callback_data="back")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Клавіатура для улюблених міст
def get_favorite_cities_keyboard(user_id):
    cities = get_favorite_cities(user_id)
    if not cities:
        return None
    keyboard = [[InlineKeyboardButton(city, callback_data=f"city_{city}")] for city in cities]
    keyboard.append([InlineKeyboardButton("Ввести вручну", callback_data="manual")])
    return InlineKeyboardMarkup(keyboard)

# Обробка /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    keyboard = get_favorite_cities_keyboard(user_id)
    if keyboard:
        await update.message.reply_text(
            "Оберіть улюблене місто або введіть нове (через кому):",
            reply_markup=keyboard
        )
    else:
        await update.message.reply_text(
            "Введіть одне або кілька міст через кому (наприклад, Київ, Охтирка).\n"
            "Команди:\n"
            "/notify <час> – увімкнути оповіщення (наприклад, /notify 15:00, 18:15)\n"
            "/stopnotify – вимкнути оповіщення\n"
            "/history – останні 5 запитів\n"
            "/alert on/off – сповіщення про екстремальну погоду\n"
            "додати <місто> – додати улюблене місто\n"
            "улюблені – список улюблених міст\n"
            "/compare <місто1, місто2> – порівняти погоду"
        )

# Обробка текстових повідомлень
# Обробка текстових повідомлень
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip()

    if text.startswith("додати "):
        city = text[7:].strip().title()
        save_favorite_city(user_id, city)
        await update.message.reply_text(f"Місто {city} додано до улюблених!")
        return

    if text.lower() == "улюблені":
        cities = get_favorite_cities(user_id)
        if cities:
            await update.message.reply_text(f"Ваші улюблені міста: {', '.join(cities)}")
        else:
            await update.message.reply_text("У вас немає улюблених міст.")
        return

    cities = [city.strip().title() for city in text.split(",") if city.strip()]
    if not cities:
        await update.message.reply_text("Введіть хоча б одне місто.")
        return

    context.user_data["cities"] = cities
    await update.message.reply_text("Виберіть тип прогнозу:", reply_markup=get_weather_keyboard())  # Виправлено

# Обробка кнопок
async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "back":
        keyboard = get_favorite_cities_keyboard(user_id)
        if keyboard:
            await query.message.edit_text(
                "Оберіть улюблене місто або введіть нове (через кому):",
                reply_markup=keyboard
            )
        else:
            await query.message.edit_text("Введіть одне або кілька міст через кому.")
        if "cities" in context.user_data:
            del context.user_data["cities"]
        return

    if query.data.startswith("city_"):
        city = query.data[5:]
        context.user_data["cities"] = [city]
        await query.message.edit_text(f"Обрано: {city}. Виберіть тип прогнозу:", reply_markup=get_weather_keyboard())
        return

    if query.data == "manual":
        await query.message.edit_text("Введіть одне або кілька міст через кому.")
        return

    if "cities" not in context.user_data:
        await query.message.edit_text("Спочатку введіть міста.")
        return

    cities = context.user_data["cities"]
    for city in cities:
        if query.data == "current":
            result = get_current_weather(city)
            save_request(user_id, city, "current")
            await query.message.reply_text(result)
        elif query.data == "forecast":
            result, chart = get_forecast(city)
            save_request(user_id, city, "forecast")
            await query.message.reply_text(result)
            if chart:
                await query.message.reply_photo(photo=io.BytesIO(base64.b64decode(chart)))
    
    await query.message.edit_text("Введіть нові міста або скористайтеся іншими командами.")
    del context.user_data["cities"]

# Обробка /notify
async def notify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    args = context.args
    if not args:
        await update.message.reply_text("Введіть час у форматі HH:MM, наприклад, /notify 15:00 або /notify 15:00, 18:15")
        return

    times = [t.strip() for t in " ".join(args).split(",") if t.strip()]
    for t in times:
        try:
            hour, minute = map(int, t.split(":"))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
            notify_time = f"{hour:02d}:{minute:02d}"
            save_notification_time(user_id, notify_time)
            scheduler.add_job(
                send_notification,
                CronTrigger(hour=hour, minute=minute),
                args=[context, user_id, context.bot],
                id=f"notify_{user_id}_{notify_time}"
            )
            await update.message.reply_text(f"Оповіщення встановлено на {notify_time}.")
        except ValueError:
            await update.message.reply_text(f"Невірний формат часу: {t}. Використовуйте HH:MM.")

# Обробка /stopnotify
async def stop_notify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    times = get_notification_times(user_id)
    if not times:
        await update.message.reply_text("У вас немає активних оповіщень.")
        return
    for t in times:
        scheduler.remove_job(f"notify_{user_id}_{t}")
    delete_notifications(user_id)
    await update.message.reply_text("Оповіщення вимкнено.")

# Обробка /history
async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    history = get_history(user_id)
    if not history:
        await update.message.reply_text("Історія запитів порожня.")
        return
    response = "📜 Останні запити:\n"
    for city, req_type, timestamp in history:
        response += f"{timestamp} - {city} ({'зараз' if req_type == 'current' else 'прогноз'})\n"
    await update.message.reply_text(response)

# Обробка /alert
async def alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if context.args and context.args[0].lower() == "on":
        save_alert_setting(user_id, 1)
        scheduler.add_job(
            check_extreme_weather,
            CronTrigger(hour="*/6"),
            args=[context, user_id, context.bot],
            id=f"alert_{user_id}"
        )
        await update.message.reply_text("Сповіщення про екстремальну погоду увімкнено.")
    elif context.args and context.args[0].lower() == "off":
        save_alert_setting(user_id, 0)
        try:
            scheduler.remove_job(f"alert_{user_id}")
        except:
            pass
        await update.message.reply_text("Сповіщення про екстремальну погоду вимкнено.")
    else:
        await update.message.reply_text("Використовуйте: /alert on або /alert off")

# Обробка /compare
async def compare(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    args = " ".join(context.args).split(",")
    cities = [city.strip().title() for city in args if city.strip()]
    if len(cities) != 2:
        await update.message.reply_text("Введіть рівно два міста, наприклад: /compare Київ, Охтирка")
        return
    
    weather1 = get_current_weather(cities[0])
    weather2 = get_current_weather(cities[1])
    comparison = f"Порівняння погоди:\n\n{weather1}\n\n{weather2}\n\n"
    
    try:
        params1 = {"q": cities[0], "appid": API_KEY, "units": "metric"}
        params2 = {"q": cities[1], "appid": API_KEY, "units": "metric"}
        temp1 = requests.get(WEATHER_URL, params=params1).json().get("main", {}).get("temp", 0)
        temp2 = requests.get(WEATHER_URL, params=params2).json().get("main", {}).get("temp", 0)
        
        if temp1 > temp2:
            comparison += f"У {cities[0]} тепліше! 🌞"
        elif temp2 > temp1:
            comparison += f"У {cities[1]} тепліше! 🌞"
        else:
            comparison += "Температура однакова! 😊"
    except:
        comparison += "Не вдалося порівняти температури."
    
    save_request(user_id, cities[0], "compare")
    save_request(user_id, cities[1], "compare")
    await update.message.reply_text(comparison)

# Завантаження запланованих завдань
def load_scheduled_jobs(application):
    conn = sqlite3.connect("/app/data/weather_bot.db")
    c = conn.cursor()
    c.execute("SELECT user_id, notify_time FROM notifications")
    for user_id, notify_time in c.fetchall():
        hour, minute = map(int, notify_time.split(":"))
        scheduler.add_job(
            send_notification,
            CronTrigger(hour=hour, minute=minute),
            args=[None, user_id, application.bot],
            id=f"notify_{user_id}_{notify_time}"
        )
    c.execute("SELECT user_id FROM alerts WHERE enabled = 1")
    for (user_id,) in c.fetchall():
        scheduler.add_job(
            check_extreme_weather,
            CronTrigger(hour="*/6"),
            args=[None, user_id, application.bot],
            id=f"alert_{user_id}"
        )
    conn.close()

# Головна функція
def main():
    global application
    init_db()
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "your_telegram_bot_token")
    application = Application.builder().token(bot_token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("notify", notify))
    application.add_handler(CommandHandler("stopnotify", stop_notify))
    application.add_handler(CommandHandler("history", history))
    application.add_handler(CommandHandler("alert", alert))
    application.add_handler(CommandHandler("compare", compare))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(handle_button))

    load_scheduled_jobs(application)

    webhook_url = os.getenv("WEBHOOK_URL", "https://your-render-service.onrender.com/webhook")
    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 8443)),
        url_path="/webhook",
        webhook_url=webhook_url
    )

if __name__ == "__main__":
    main()