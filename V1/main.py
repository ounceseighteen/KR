"""
main.py — Создание базы данных SQLite3
Информационная система кинотеатра
Курсовая работа: Сопровождение информационной системы кинотеатра
"""

import sqlite3
import os

DB_NAME = "кинотеатр.db"


def create_database():
    if os.path.exists(DB_NAME):
        os.remove(DB_NAME)
        print(f"Старая база данных '{DB_NAME}' удалена.")

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("PRAGMA foreign_keys = ON;")

    # 1. Залы
    cursor.execute("""
        CREATE TABLE залы (
            код_зала    INTEGER PRIMARY KEY AUTOINCREMENT,
            название    TEXT    NOT NULL,
            вместимость INTEGER NOT NULL CHECK(вместимость > 0),
            тип_зала    TEXT    NOT NULL CHECK(тип_зала IN ('2D', '3D', 'IMAX', '4DX')),
            активен     INTEGER NOT NULL DEFAULT 1
        );
    """)

    # 2. Фильмы
    cursor.execute("""
        CREATE TABLE фильмы (
            код_фильма         INTEGER PRIMARY KEY AUTOINCREMENT,
            название           TEXT    NOT NULL,
            жанр               TEXT    NOT NULL,
            длительность_мин   INTEGER NOT NULL CHECK(длительность_мин > 0),
            возрастной_рейтинг TEXT    NOT NULL CHECK(возрастной_рейтинг IN ('0+', '6+', '12+', '16+', '18+')),
            язык               TEXT    NOT NULL DEFAULT 'Русский',
            описание           TEXT,
            год_выпуска        INTEGER
        );
    """)

    # 3. Сеансы (код_билета убран — он не нужен в схеме)
    cursor.execute("""
        CREATE TABLE сеансы (
            код_сеанса  INTEGER PRIMARY KEY AUTOINCREMENT,
            код_фильма  INTEGER NOT NULL REFERENCES фильмы(код_фильма) ON DELETE CASCADE,
            код_зала    INTEGER NOT NULL REFERENCES залы(код_зала)      ON DELETE CASCADE,
            начало      TEXT    NOT NULL,
            окончание   TEXT    NOT NULL,
            цена_руб    REAL    NOT NULL CHECK(цена_руб >= 0),
            формат      TEXT    NOT NULL CHECK(формат IN ('2D', '3D', 'IMAX', '4DX'))
        );
    """)

    # 4. Места
    cursor.execute("""
        CREATE TABLE места (
            код_места   INTEGER PRIMARY KEY AUTOINCREMENT,
            код_зала    INTEGER NOT NULL REFERENCES залы(код_зала) ON DELETE CASCADE,
            ряд         INTEGER NOT NULL CHECK(ряд > 0),
            номер_места INTEGER NOT NULL CHECK(номер_места > 0),
            тип_места   TEXT    NOT NULL CHECK(тип_места IN ('стандарт', 'вип', 'диван')),
            UNIQUE(код_зала, ряд, номер_места)
        );
    """)

    # 5. Клиенты
    # ИЗМЕНЕНИЕ: добавлены поля пароль_хэш (для входа через client_app.py)
    #             и UNIQUE-ограничение на телефон (он теперь обязателен при регистрации).
    cursor.execute("""
        CREATE TABLE клиенты (
            код_клиента       INTEGER PRIMARY KEY AUTOINCREMENT,
            полное_имя        TEXT    NOT NULL,
            электронная_почта TEXT    UNIQUE,
            телефон           TEXT    NOT NULL UNIQUE,
            бонусные_баллы    INTEGER NOT NULL DEFAULT 0 CHECK(бонусные_баллы >= 0),
            дата_регистрации  TEXT    NOT NULL,
            пароль_хэш        TEXT
        );
    """)

    # 6. Сотрудники
    cursor.execute("""
        CREATE TABLE сотрудники (
            код_сотрудника  INTEGER PRIMARY KEY AUTOINCREMENT,
            полное_имя      TEXT    NOT NULL,
            должность       TEXT    NOT NULL CHECK(должность IN (
                                'кассир', 'администратор', 'технический специалист', 'менеджер', 'охранник')),
            логин           TEXT    NOT NULL UNIQUE,
            пароль          TEXT    NOT NULL,
            дата_найма      TEXT    NOT NULL,
            активен         INTEGER NOT NULL DEFAULT 1
        );
    """)

    # 7. Билеты
    cursor.execute("""
        CREATE TABLE билеты (
            код_билета    INTEGER PRIMARY KEY AUTOINCREMENT,
            код_сеанса    INTEGER NOT NULL REFERENCES сеансы(код_сеанса)  ON DELETE CASCADE,
            код_места     INTEGER NOT NULL REFERENCES места(код_места),
            код_клиента   INTEGER          REFERENCES клиенты(код_клиента),
            цена_руб      REAL    NOT NULL CHECK(цена_руб >= 0),
            статус        TEXT    NOT NULL DEFAULT 'забронирован'
                                  CHECK(статус IN ('забронирован', 'оплачен', 'отменён', 'использован')),
            дата_покупки  TEXT    NOT NULL,
            способ_оплаты TEXT    CHECK(способ_оплаты IN ('наличные', 'карта', 'онлайн')),
            UNIQUE(код_сеанса, код_места)
        );
    """)

    conn.commit()
    conn.close()

    print(f"База данных '{DB_NAME}' успешно создана.")
    print("Созданные таблицы:")
    tables = [
        "  • залы        — залы кинотеатра",
        "  • фильмы      — каталог фильмов",
        "  • сеансы      — расписание сеансов",
        "  • места       — места в залах",
        "  • клиенты     — клиенты (CRM)",
        "  • сотрудники  — сотрудники",
        "  • билеты      — билеты и бронирования",
    ]
    for t in tables:
        print(t)


def _to_iso(col):
    """Конвертирует ДД.ММ.ГГГГ ЧЧ:ММ → ГГГГ-ММ-ДД ЧЧ:ММ для сравнения в SQLite."""
    return (f"substr({col},7,4)||'-'||substr({col},4,2)||'-'||substr({col},1,2)"
            f"||' '||substr({col},12,5)")


def query_current_sessions(cursor):
    """Вывести сеансы, которые идут сейчас."""
    cursor.execute(f"""
        SELECT
            с.код_сеанса,
            ф.название  AS фильм,
            з.название  AS зал,
            с.начало,
            с.окончание,
            с.формат,
            с.цена_руб
        FROM сеансы с
        JOIN фильмы ф ON ф.код_фильма = с.код_фильма
        JOIN залы   з ON з.код_зала   = с.код_зала
        WHERE strftime('%Y-%m-%d %H:%M', 'now', 'localtime')
              BETWEEN {_to_iso('с.начало')} AND {_to_iso('с.окончание')}
        ORDER BY с.начало;
    """)
    rows = cursor.fetchall()
    print("\nСеансы, идущие прямо сейчас")
    if not rows:
        print("  Нет активных сеансов.")
    else:
        print(f"  {'№':>4}  {'Фильм':<30}  {'Зал':<15}  {'Начало':<16}  {'Окончание':<16}  {'Формат':<4}  {'Цена':>8}")
        print("  " + "-" * 100)
        for r in rows:
            print(f"  {r[0]:>4}  {r[1]:<30}  {r[2]:<15}  {r[3]:<16}  {r[4]:<16}  {r[5]:<4}  {r[6]:>7.2f}₽")


def query_most_popular_film(cursor):
    """Вывести самый популярный фильм (по количеству сеансов в расписании)."""
    cursor.execute("""
        SELECT
            ф.название,
            ф.жанр,
            ф.год_выпуска,
            COUNT(с.код_сеанса) AS кол_во_сеансов
        FROM фильмы ф
        JOIN сеансы с ON с.код_фильма = ф.код_фильма
        GROUP BY ф.код_фильма
        ORDER BY кол_во_сеансов DESC
        LIMIT 1;
    """)
    row = cursor.fetchone()
    print("\n=== Самый популярный фильм ===")
    if not row:
        print("  Нет данных.")
    else:
        print(f"  Название        : {row[0]}")
        print(f"  Жанр            : {row[1]}")
        print(f"  Год выпуска     : {row[2]}")
        print(f"  Кол-во сеансов  : {row[3]}")


def query_least_filled_hall(cursor):
    """Вывести зал с наименьшей заполняемостью — считаем реальные билеты из таблицы билеты."""
    cursor.execute("""
        SELECT
            з.название,
            з.вместимость,
            з.тип_зала,
            COUNT(DISTINCT с.код_сеанса)                                        AS сеансов,
            з.вместимость * COUNT(DISTINCT с.код_сеанса)                        AS макс_мест,
            COUNT(б.код_билета)                                                 AS продано,
            ROUND(
                100.0 * COUNT(б.код_билета)
                / NULLIF(з.вместимость * COUNT(DISTINCT с.код_сеанса), 0),
            2)                                                                  AS заполняемость_проц
        FROM залы з
        LEFT JOIN сеансы  с ON с.код_зала   = з.код_зала
        LEFT JOIN билеты  б ON б.код_сеанса = с.код_сеанса
                           AND б.статус IN ('оплачен', 'использован')
        WHERE з.активен = 1
        GROUP BY з.код_зала
        ORDER BY заполняемость_проц ASC
        LIMIT 1;
    """)
    row = cursor.fetchone()
    print("\n=== Зал с наименьшей заполняемостью ===")
    if not row:
        print("  Нет данных.")
    else:
        print(f"  Зал             : {row[0]}")
        print(f"  Тип             : {row[2]}")
        print(f"  Вместимость     : {row[1]} мест")
        print(f"  Всего сеансов   : {row[3]}")
        print(f"  Макс. мест      : {row[4]}")
        print(f"  Продано билетов : {row[5]}")
        print(f"  Заполняемость   : {row[6] if row[6] is not None else 0}%")


def show_menu():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

    while True:
        print("\nИнформационная система кинотеатра")
        print("")
        print("1 — Сеансы, идущие прямо сейчас")
        print("2 — Самый популярный фильм")
        print("3 — Зал с наименьшей заполняемостью")
        print("0 — Выход")

        choice = input("\nВыберите пункт меню: ").strip()

        if choice == "1":
            query_current_sessions(cursor)
        elif choice == "2":
            query_most_popular_film(cursor)
        elif choice == "3":
            query_least_filled_hall(cursor)
        elif choice == "0":
            print("До свидания!")
            break
        else:
            print("  Неверный ввод. Введите число от 0 до 3.")

    conn.close()


if __name__ == "__main__":
    if not os.path.exists(DB_NAME):
        create_database()
    show_menu()
