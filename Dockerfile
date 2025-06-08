FROM python:3.9-slim

WORKDIR /app

# Копіюємо лише requirements.txt для кешування залежностей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копіюємо решту файлів
COPY . .

# Налаштування змінних середовища
ENV PYTHONUNBUFFERED=1
ENV PORT=8443

# Створюємо директорію для бази даних
RUN mkdir -p /app/data

# Відкриваємо порт
EXPOSE 8443

# Запускаємо додаток
CMD ["python", "weather_bot.py"]