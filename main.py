from datetime import datetime
import os
import re  # ➕ ДОБАВЛЕНО: для валидации имени таблицы
from contextlib import contextmanager, asynccontextmanager

import mysql.connector
from fastapi import FastAPI, Request, Depends, Header, HTTPException
from typing import Optional


# --- 1. Конфигурация ---
# Считываем конфигурацию БД из переменных окружения
db_host = os.environ.get('DB_HOST', '127.0.0.1')
db_user = os.environ.get('DB_USER', 'app')
db_password = os.environ.get('DB_PASSWORD', 'very_strong')
db_name = os.environ.get('DB_NAME', 'example')
db_table = os.environ.get('DB_TABLE', 'requests')  # ➕ ДОБАВЛЕНО: имя таблицы из ENV

# ➕ ДОБАВЛЕНО: валидация — защита от SQL-инъекции через имя таблицы
if not re.fullmatch(r'[A-Za-z0-9_]+', db_table):
    raise ValueError(f"Недопустимое имя таблицы: {db_table}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Код, который выполнится перед запуском приложения
    print("Приложение запускается...")
    if ensure_table_exists():
        print(f"Соединение с БД установлено и таблица '{db_table}' готова к работе.")  # 🔄 ИЗМЕНЕНО: было 'requests'
    else:
        print("БД недоступна при старте. Таблица будет создана при первом запросе.")

    yield

    # Код, который выполнится при остановке приложения
    print("Приложение останавливается.")


# Создаем экземпляр FastAPI с использованием lifespan
app = FastAPI(
    title="Shvirtd Example FastAPI",
    description="Учебный проект, FastAPI+Docker.",
    version="1.0.0",
    lifespan=lifespan
)


# --- 2. Управление соединением с БД ---
@contextmanager
def get_db_connection():
    db = None
    try:
        db = mysql.connector.connect(
            host=db_host,
            user=db_user,
            password=db_password,
            database=db_name
        )
        yield db
    finally:
        if db is not None and db.is_connected():
            db.close()


# --- 2.1. Функция создания таблицы ---
def ensure_table_exists():
    """Создает таблицу если она не существует"""
    try:
        with get_db_connection() as db:
            cursor = db.cursor()
            # 🔄 ИЗМЕНЕНО: убран префикс {db_name}., имя таблицы берётся из db_table
            # 🔄 ИЗМЕНЕНО: имя таблицы в обратных кавычках для безопасности
            create_table_query = f"""
            CREATE TABLE IF NOT EXISTS `{db_table}` (
                id INT AUTO_INCREMENT PRIMARY KEY,
                request_date DATETIME,
                request_ip VARCHAR(255)
            )
            """
            cursor.execute(create_table_query)
            db.commit()
            cursor.close()
            return True
    except mysql.connector.Error as err:
        print(f"Ошибка при создании таблицы: {err}")
        return False


# --- 3. Зависимость для получения IP ---
def get_client_ip(x_real_ip: Optional[str] = Header(None)):
    return x_real_ip


# --- 4. Вспомогательная функция для INSERT ---
# ➕ ДОБАВЛЕНО: вынесено из эндпоинта /, чтобы убрать дублирование try/except
def _insert_request(current_time: str, ip: Optional[str]) -> None:
    """Вставляет запись в таблицу. При ошибке — пересоздаёт таблицу и повторяет."""
    query = f"INSERT INTO `{db_table}` (request_date, request_ip) VALUES (%s, %s)"  # 🔄 ИЗМЕНЕНО: db_table вместо requests
    values = (current_time, ip)
    try:
        with get_db_connection() as db:
            cursor = db.cursor()
            cursor.execute(query, values)
            db.commit()
            cursor.close()
    except mysql.connector.Error as err:
        print(f"Ошибка INSERT: {err}. Пересоздаю таблицу.")
        ensure_table_exists()
        with get_db_connection() as db:
            cursor = db.cursor()
            cursor.execute(query, values)
            db.commit()
            cursor.close()


# --- 5. Основной эндпоинт ---
@app.get("/")
def index(request: Request, ip_address: Optional[str] = Depends(get_client_ip)):
    final_ip = ip_address  # Только из X-Forwarded-For, без fallback

    now = datetime.now()
    current_time = now.strftime("%Y-%m-%d %H:%M:%S")

    # 🔄 ИЗМЕНЕНО: вместо дублированного try/except — вызов вспомогательной функции
    _insert_request(current_time, final_ip)

    # Подсказка для студентов при неправильном обращении
    if final_ip is None:
        ip_display = "похоже, что вы направляете запрос в неверный порт(например curl http://127.0.0.1:5000). Правильное выполнение задания - отправить запрос в порт 8090."
    else:
        ip_display = final_ip

    return f'TIME: {current_time}, IP: {ip_display}'


# --- 5. Отладочный эндпоинт ---
@app.get("/debug")
def debug_headers(request: Request):
    """Показывает все заголовки для отладки откуда берется IP"""
    return {
        "headers": dict(request.headers),
        "client_host": request.client.host if request.client else None,
        "x_forwarded_for": request.headers.get('x-forwarded-for'),
        "real_ip": request.headers.get('x-real-ip'),
        "forwarded": request.headers.get('forwarded')
    }


# --- 6. Вспомогательная функция для SELECT ---
# ➕ ДОБАВЛЕНО: вынесено из эндпоинта /requests, чтобы убрать дублирование try/except
def _fetch_requests() -> list:
    query = (f"SELECT id, request_date, request_ip FROM `{db_table}` "  # 🔄 ИЗМЕНЕНО: db_table вместо requests
             f"ORDER BY id DESC LIMIT 50")
    with get_db_connection() as db:
        cursor = db.cursor()
        cursor.execute(query)
        records = cursor.fetchall()
        cursor.close()
        return [
            {
                "id": r[0],
                "request_date": r[1].strftime("%Y-%m-%d %H:%M:%S") if r[1] else None,
                "request_ip": r[2],
            }
            for r in records
        ]


# --- 6.1. Эндпоинт для просмотра записей в БД ---
@app.get("/requests")
def get_requests():
    """Возвращает все записи из таблицы для проверки"""
    try:
        result = _fetch_requests()  # 🔄 ИЗМЕНЕНО: вызов вспомогательной функции
    except mysql.connector.Error as err:
        print(f"Ошибка SELECT: {err}. Пересоздаю таблицу.")
        ensure_table_exists()
        result = _fetch_requests()

    return {
        "total_records": len(result),
        "records": result,
    }


# --- 7. Запуск приложения ---
# Для запуска этого файла используется ASGI-сервер, например, uvicorn.
# Команда: uvicorn main:app --reload
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=5000)