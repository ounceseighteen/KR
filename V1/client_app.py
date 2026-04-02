"""
client_app.py — Клиентское Flask-приложение
Информационная система кинотеатра
Только для клиентов: регистрация, вход, расписание, покупка билетов, личный кабинет.
"""

import sqlite3
import hashlib
import os
from datetime import datetime
from functools import wraps
from flask import (Flask, render_template, g, request, redirect,
                   url_for, session, flash)

app = Flask(__name__)
app.secret_key = "cinema-client-secret-2026"
DB_NAME = "кинотеатр.db"


# ── БД ────────────────────────────────────────────────────────────────────────
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_NAME)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON;")
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _to_iso(col):
    return (f"substr({col},7,4)||'-'||substr({col},4,2)||'-'||substr({col},1,2)"
            f"||' '||substr({col},12,5)")


def hash_password(password: str) -> str:
    """SHA-256 хэш пароля. Замените на bcrypt в продакшн-среде."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


# ── Авторизация клиента ───────────────────────────────────────────────────────
def client_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "client_id" not in session:
            flash("Необходимо войти в систему.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# ── Регистрация ───────────────────────────────────────────────────────────────
@app.route("/register", methods=["GET", "POST"])
def register():
    if "client_id" in session:
        return redirect(url_for("index"))

    if request.method == "POST":
        full_name = request.form.get("полное_имя", "").strip()
        phone     = request.form.get("телефон", "").strip()
        email     = request.form.get("электронная_почта", "").strip() or None
        password  = request.form.get("пароль", "").strip()
        password2 = request.form.get("пароль2", "").strip()

        # Валидация
        if not full_name:
            flash("ФИО обязательно.", "danger")
            return render_template("register.html")
        if not phone:
            flash("Номер телефона обязателен.", "danger")
            return render_template("register.html")
        if not password:
            flash("Пароль обязателен.", "danger")
            return render_template("register.html")
        if password != password2:
            flash("Пароли не совпадают.", "danger")
            return render_template("register.html")
        if len(password) < 6:
            flash("Пароль должен быть не менее 6 символов.", "danger")
            return render_template("register.html")

        db = get_db()

        # Проверка уникальности телефона
        existing = db.execute(
            "SELECT код_клиента FROM клиенты WHERE телефон=?", (phone,)
        ).fetchone()
        if existing:
            flash("Клиент с таким номером телефона уже зарегистрирован.", "danger")
            return render_template("register.html")

        # Проверка уникальности email (если указан)
        if email:
            existing_email = db.execute(
                "SELECT код_клиента FROM клиенты WHERE электронная_почта=?", (email,)
            ).fetchone()
            if existing_email:
                flash("Клиент с такой электронной почтой уже зарегистрирован.", "danger")
                return render_template("register.html")

        try:
            db.execute("""
                INSERT INTO клиенты
                    (полное_имя, электронная_почта, телефон, бонусные_баллы, дата_регистрации, пароль_хэш)
                VALUES (?, ?, ?, 0, ?, ?)
            """, (
                full_name,
                email,
                phone,
                datetime.now().strftime("%d.%m.%Y"),
                hash_password(password),
            ))
            db.commit()
            flash("Регистрация прошла успешно! Войдите в систему.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Ошибка при регистрации. Проверьте введённые данные.", "danger")

    return render_template("register.html")


# ── Вход ──────────────────────────────────────────────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    if "client_id" in session:
        return redirect(url_for("index"))

    if request.method == "POST":
        identifier = request.form.get("идентификатор", "").strip()  # email или телефон
        password   = request.form.get("пароль", "").strip()

        if not identifier or not password:
            flash("Введите email или телефон и пароль.", "danger")
            return render_template("login.html")

        db = get_db()
        # Ищем по email ИЛИ телефону
        client = db.execute("""
            SELECT * FROM клиенты
            WHERE (электронная_почта=? OR телефон=?)
              AND пароль_хэш=?
        """, (identifier, identifier, hash_password(password))).fetchone()

        if client:
            session["client_id"]   = client["код_клиента"]
            session["client_name"] = client["полное_имя"]
            flash(f"Добро пожаловать, {client['полное_имя']}!", "success")
            return redirect(url_for("index"))

        flash("Неверный email/телефон или пароль.", "danger")

    return render_template("login.html")


# ── Выход ─────────────────────────────────────────────────────────────────────
@app.route("/logout")
def logout():
    session.clear()
    flash("Вы вышли из системы.", "info")
    return redirect(url_for("login"))


# ── Главная / Расписание ──────────────────────────────────────────────────────
@app.route("/")
def index():
    db = get_db()

    # Сеансы на ближайшие 7 дней
    rows = db.execute(f"""
        SELECT с.код_сеанса,
               substr(с.начало,7,4)||'-'||substr(с.начало,4,2)||'-'||substr(с.начало,1,2) AS дата,
               ф.название             AS фильм,
               ф.жанр,
               ф.возрастной_рейтинг,
               ф.длительность_мин,
               з.название             AS зал,
               с.начало, с.окончание,
               с.формат, с.цена_руб
        FROM сеансы с
        JOIN фильмы ф ON ф.код_фильма = с.код_фильма
        JOIN залы   з ON з.код_зала   = с.код_зала
        WHERE {_to_iso('с.начало')} >= strftime('%Y-%m-%d','now','localtime')
          AND {_to_iso('с.начало')} <= strftime('%Y-%m-%d','now','localtime','+6 days')
        ORDER BY {_to_iso('с.начало')}
    """).fetchall()

    from collections import OrderedDict
    by_date = OrderedDict()
    for r in rows:
        by_date.setdefault(r["дата"], []).append(r)

    genres  = [r[0] for r in db.execute("SELECT DISTINCT жанр FROM фильмы ORDER BY жанр").fetchall()]
    formats = ["2D", "3D", "IMAX", "4DX"]

    return render_template("index.html", by_date=by_date,
                           genres=genres, formats=formats)


# ── Детальная страница сеанса + выбор места ───────────────────────────────────
@app.route("/session/<int:sid>")
def session_detail(sid):
    db = get_db()
    ses = db.execute(f"""
        SELECT с.*, ф.название AS фильм, ф.описание, ф.жанр,
               ф.возрастной_рейтинг, ф.длительность_мин, ф.год_выпуска,
               з.название AS зал, з.тип_зала
        FROM сеансы с
        JOIN фильмы ф ON ф.код_фильма = с.код_фильма
        JOIN залы   з ON з.код_зала   = с.код_зала
        WHERE с.код_сеанса = ?
    """, (sid,)).fetchone()

    if not ses:
        flash("Сеанс не найден.", "danger")
        return redirect(url_for("index"))

    # Все места зала с пометкой — свободно/занято
    seats = db.execute("""
        SELECT м.код_места, м.ряд, м.номер_места, м.тип_места,
               CASE WHEN б.код_билета IS NOT NULL THEN 1 ELSE 0 END AS занято
        FROM места м
        LEFT JOIN билеты б ON б.код_места  = м.код_места
                          AND б.код_сеанса = ?
                          AND б.статус NOT IN ('отменён')
        WHERE м.код_зала = (SELECT код_зала FROM сеансы WHERE код_сеанса=?)
        ORDER BY м.ряд, м.номер_места
    """, (sid, sid)).fetchall()

    return render_template("session_detail.html", ses=ses, seats=seats)


# ── Покупка / Бронирование билета ────────────────────────────────────────────
@app.route("/book/<int:sid>/<int:seat_id>", methods=["GET", "POST"])
@client_required
def book(sid, seat_id):
    db = get_db()

    # Проверяем что место свободно
    busy = db.execute("""
        SELECT код_билета FROM билеты
        WHERE код_сеанса=? AND код_места=? AND статус NOT IN ('отменён')
    """, (sid, seat_id)).fetchone()
    if busy:
        flash("Это место уже занято. Выберите другое.", "danger")
        return redirect(url_for("session_detail", sid=sid))

    ses = db.execute(f"""
        SELECT с.*, ф.название AS фильм, з.название AS зал
        FROM сеансы с
        JOIN фильмы ф ON ф.код_фильма=с.код_фильма
        JOIN залы   з ON з.код_зала=с.код_зала
        WHERE с.код_сеанса=?
    """, (sid,)).fetchone()
    seat = db.execute("SELECT * FROM места WHERE код_места=?", (seat_id,)).fetchone()

    if not ses or not seat:
        flash("Сеанс или место не найдены.", "danger")
        return redirect(url_for("index"))

    if request.method == "POST":
        action  = request.form.get("действие")   # "купить" или "забронировать"
        payment = request.form.get("способ_оплаты") or None

        if action == "купить" and not payment:
            flash("Выберите способ оплаты.", "danger")
            return render_template("book.html", ses=ses, seat=seat)

        status   = "оплачен" if action == "купить" else "забронирован"
        now_str  = datetime.now().strftime("%d.%m.%Y %H:%M")
        client_id = session["client_id"]

        try:
            db.execute("""
                INSERT INTO билеты
                    (код_сеанса, код_места, код_клиента, цена_руб, статус, дата_покупки, способ_оплаты)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (sid, seat_id, client_id, ses["цена_руб"], status, now_str, payment))
            db.commit()
            word = "куплен" if action == "купить" else "забронирован"
            flash(f"Билет успешно {word}!", "success")
            return redirect(url_for("profile"))
        except sqlite3.IntegrityError:
            flash("Это место только что заняли. Выберите другое.", "danger")
            return redirect(url_for("session_detail", sid=sid))

    return render_template("book.html", ses=ses, seat=seat)


# ── Отмена бронирования клиентом ─────────────────────────────────────────────
@app.route("/ticket/<int:tid>/cancel", methods=["POST"])
@client_required
def cancel_ticket(tid):
    db = get_db()
    ticket = db.execute("""
        SELECT * FROM билеты WHERE код_билета=? AND код_клиента=?
    """, (tid, session["client_id"])).fetchone()

    if not ticket:
        flash("Билет не найден.", "danger")
        return redirect(url_for("profile"))

    if ticket["статус"] not in ("забронирован", "оплачен"):
        flash("Этот билет нельзя отменить.", "warning")
        return redirect(url_for("profile"))

    db.execute("UPDATE билеты SET статус='отменён' WHERE код_билета=?", (tid,))
    db.commit()
    flash("Бронирование отменено.", "info")
    return redirect(url_for("profile"))


# ── Личный кабинет ────────────────────────────────────────────────────────────
@app.route("/profile")
@client_required
def profile():
    db  = get_db()
    cid = session["client_id"]

    client = db.execute("SELECT * FROM клиенты WHERE код_клиента=?", (cid,)).fetchone()
    tickets = db.execute(f"""
        SELECT б.код_билета, б.статус, б.цена_руб, б.дата_покупки,
               б.способ_оплаты,
               ф.название AS фильм, с.начало, з.название AS зал,
               м.ряд, м.номер_места, м.тип_места
        FROM билеты б
        JOIN сеансы с ON с.код_сеанса = б.код_сеанса
        JOIN фильмы ф ON ф.код_фильма = с.код_фильма
        JOIN залы   з ON з.код_зала   = с.код_зала
        JOIN места  м ON м.код_места  = б.код_места
        WHERE б.код_клиента = ?
        ORDER BY {_to_iso('б.дата_покупки')} DESC
    """, (cid,)).fetchall()

    return render_template("profile.html", client=client, tickets=tickets)


# ── Редактирование профиля ────────────────────────────────────────────────────
@app.route("/profile/edit", methods=["GET", "POST"])
@client_required
def profile_edit():
    db  = get_db()
    cid = session["client_id"]
    client = db.execute("SELECT * FROM клиенты WHERE код_клиента=?", (cid,)).fetchone()

    if request.method == "POST":
        full_name = request.form.get("полное_имя", "").strip()
        phone     = request.form.get("телефон", "").strip()
        email     = request.form.get("электронная_почта", "").strip() or None

        if not full_name or not phone:
            flash("ФИО и телефон обязательны.", "danger")
            return render_template("profile_edit.html", client=client)

        # Уникальность телефона (исключая себя)
        dup_phone = db.execute(
            "SELECT код_клиента FROM клиенты WHERE телефон=? AND код_клиента!=?",
            (phone, cid)
        ).fetchone()
        if dup_phone:
            flash("Этот номер телефона уже используется другим аккаунтом.", "danger")
            return render_template("profile_edit.html", client=client)

        # Уникальность email
        if email:
            dup_email = db.execute(
                "SELECT код_клиента FROM клиенты WHERE электронная_почта=? AND код_клиента!=?",
                (email, cid)
            ).fetchone()
            if dup_email:
                flash("Этот email уже используется другим аккаунтом.", "danger")
                return render_template("profile_edit.html", client=client)

        try:
            db.execute("""
                UPDATE клиенты SET полное_имя=?, телефон=?, электронная_почта=?
                WHERE код_клиента=?
            """, (full_name, phone, email, cid))
            db.commit()
            session["client_name"] = full_name
            flash("Профиль обновлён.", "success")
            return redirect(url_for("profile"))
        except sqlite3.IntegrityError:
            flash("Ошибка при обновлении данных.", "danger")

    return render_template("profile_edit.html", client=client)


# ── Смена пароля ──────────────────────────────────────────────────────────────
@app.route("/profile/password", methods=["GET", "POST"])
@client_required
def change_password():
    db  = get_db()
    cid = session["client_id"]

    if request.method == "POST":
        old_pw  = request.form.get("старый_пароль", "").strip()
        new_pw  = request.form.get("новый_пароль", "").strip()
        new_pw2 = request.form.get("новый_пароль2", "").strip()

        client = db.execute(
            "SELECT пароль_хэш FROM клиенты WHERE код_клиента=?", (cid,)
        ).fetchone()

        if client["пароль_хэш"] != hash_password(old_pw):
            flash("Неверный текущий пароль.", "danger")
            return render_template("change_password.html")
        if len(new_pw) < 6:
            flash("Новый пароль должен быть не менее 6 символов.", "danger")
            return render_template("change_password.html")
        if new_pw != new_pw2:
            flash("Новые пароли не совпадают.", "danger")
            return render_template("change_password.html")

        db.execute("UPDATE клиенты SET пароль_хэш=? WHERE код_клиента=?",
                   (hash_password(new_pw), cid))
        db.commit()
        flash("Пароль успешно изменён.", "success")
        return redirect(url_for("profile"))

    return render_template("change_password.html")


if __name__ == "__main__":
    if not os.path.exists(DB_NAME):
        print(f"ОШИБКА: база данных '{DB_NAME}' не найдена.")
        print("Сначала запустите: python main.py && python seed.py")
    else:
        app.run(debug=True, port=5000)
