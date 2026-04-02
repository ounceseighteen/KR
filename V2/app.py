"""
app.py — Flask-приложение v2 (полная версия)
Информационная система кинотеатра
"""

import sqlite3
import os
from datetime import datetime
from functools import wraps
from flask import (Flask, render_template, g, request, redirect,
                   url_for, session, flash)

app = Flask(__name__)
app.secret_key = "cinema-secret-key-2026"
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


# ── Авторизация ───────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "employee_id" not in session:
            flash("Необходимо войти в систему.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if session.get("role") not in roles:
                flash("Недостаточно прав для этого действия.", "danger")
                return redirect(url_for("index"))
            return f(*args, **kwargs)
        return decorated
    return decorator


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        login_ = request.form.get("login", "").strip()
        password = request.form.get("password", "").strip()
        db = get_db()
        emp = db.execute(
            "SELECT * FROM сотрудники WHERE логин=? AND пароль=? AND активен=1",
            (login_, password)
        ).fetchone()
        if emp:
            session["employee_id"] = emp["код_сотрудника"]
            session["employee_name"] = emp["полное_имя"]
            session["role"] = emp["должность"]
            flash(f"Добро пожаловать, {emp['полное_имя']}!", "success")
            return redirect(url_for("index"))
        flash("Неверный логин или пароль.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Вы вышли из системы.", "info")
    return redirect(url_for("login"))


# ── Главная ───────────────────────────────────────────────────────────────────
@app.route("/")
@login_required
def index():
    db = get_db()
    today_sessions = db.execute(f"""
        SELECT с.код_сеанса, ф.название AS фильм, ф.возрастной_рейтинг,
               з.название AS зал, с.начало, с.окончание, с.формат, с.цена_руб
        FROM сеансы с
        JOIN фильмы ф ON ф.код_фильма = с.код_фильма
        JOIN залы   з ON з.код_зала   = с.код_зала
        WHERE substr(с.начало,1,10) = strftime('%d.%m.%Y','now','localtime')
        ORDER BY с.начало
    """).fetchall()

    live_ids = {r["код_сеанса"] for r in db.execute(f"""
        SELECT с.код_сеанса FROM сеансы с
        WHERE strftime('%Y-%m-%d %H:%M','now','localtime')
              BETWEEN {_to_iso('с.начало')} AND {_to_iso('с.окончание')}
    """).fetchall()}

    top_film = db.execute("""
        SELECT ф.название, ф.жанр, ф.год_выпуска, COUNT(с.код_сеанса) AS сеансов
        FROM фильмы ф JOIN сеансы с ON с.код_фильма=ф.код_фильма
        GROUP BY ф.код_фильма ORDER BY сеансов DESC LIMIT 1
    """).fetchone()

    least_hall = db.execute("""
        SELECT з.название, з.вместимость, з.тип_зала,
               COUNT(DISTINCT с.код_сеанса) AS сеансов,
               COUNT(б.код_билета) AS продано,
               ROUND(100.0*COUNT(б.код_билета)/NULLIF(з.вместимость*COUNT(DISTINCT с.код_сеанса),0),1) AS заполняемость
        FROM залы з
        LEFT JOIN сеансы с ON с.код_зала=з.код_зала
        LEFT JOIN билеты б ON б.код_сеанса=с.код_сеанса AND б.статус IN('оплачен','использован')
        WHERE з.активен=1 GROUP BY з.код_зала ORDER BY заполняемость ASC LIMIT 1
    """).fetchone()

    return render_template("index.html", today_sessions=today_sessions,
                           live_ids=live_ids, top_film=top_film, least_hall=least_hall)


# ── Фильмы ────────────────────────────────────────────────────────────────────
@app.route("/movies")
@login_required
def movies():
    db = get_db()
    q = request.args.get("q", "").strip()
    sql = """
        SELECT ф.*, COUNT(с.код_сеанса) AS кол_сеансов
        FROM фильмы ф LEFT JOIN сеансы с ON с.код_фильма=ф.код_фильма
        {where}
        GROUP BY ф.код_фильма ORDER BY ф.название
    """
    if q:
        films = db.execute(sql.format(where="WHERE ф.название LIKE ?"),
                           (f"%{q}%",)).fetchall()
    else:
        films = db.execute(sql.format(where="")).fetchall()
    return render_template("movies.html", films=films, q=q)


@app.route("/movies/add", methods=["GET", "POST"])
@login_required
@role_required("администратор", "менеджер")
def movie_add():
    if request.method == "POST":
        db = get_db()
        db.execute("""
            INSERT INTO фильмы (название,жанр,длительность_мин,возрастной_рейтинг,язык,описание,год_выпуска)
            VALUES (?,?,?,?,?,?,?)
        """, (
            request.form["название"].strip(),
            request.form["жанр"].strip(),
            int(request.form["длительность_мин"]),
            request.form["возрастной_рейтинг"],
            request.form.get("язык", "Русский").strip(),
            request.form.get("описание", "").strip(),
            int(request.form["год_выпуска"]),
        ))
        db.commit()
        flash("Фильм добавлен.", "success")
        return redirect(url_for("movies"))
    return render_template("movie_form.html", film=None, action="add")


@app.route("/movies/<int:fid>/edit", methods=["GET", "POST"])
@login_required
@role_required("администратор", "менеджер")
def movie_edit(fid):
    db = get_db()
    film = db.execute("SELECT * FROM фильмы WHERE код_фильма=?", (fid,)).fetchone()
    if not film:
        flash("Фильм не найден.", "danger")
        return redirect(url_for("movies"))
    if request.method == "POST":
        db.execute("""
            UPDATE фильмы SET название=?,жанр=?,длительность_мин=?,
            возрастной_рейтинг=?,язык=?,описание=?,год_выпуска=?
            WHERE код_фильма=?
        """, (
            request.form["название"].strip(),
            request.form["жанр"].strip(),
            int(request.form["длительность_мин"]),
            request.form["возрастной_рейтинг"],
            request.form.get("язык", "Русский").strip(),
            request.form.get("описание", "").strip(),
            int(request.form["год_выпуска"]),
            fid,
        ))
        db.commit()
        flash("Фильм обновлён.", "success")
        return redirect(url_for("movies"))
    return render_template("movie_form.html", film=film, action="edit")


@app.route("/movies/<int:fid>/delete", methods=["POST"])
@login_required
@role_required("администратор")
def movie_delete(fid):
    db = get_db()
    db.execute("DELETE FROM фильмы WHERE код_фильма=?", (fid,))
    db.commit()
    flash("Фильм удалён.", "info")
    return redirect(url_for("movies"))


# ── Сеансы ────────────────────────────────────────────────────────────────────
@app.route("/schedule")
@login_required
def schedule():
    db = get_db()
    date_f  = request.args.get("date", "")
    genre_f = request.args.get("genre", "")
    fmt_f   = request.args.get("format", "")

    conditions = [
        f"{_to_iso('с.начало')} >= strftime('%Y-%m-%d','now','localtime')",
        f"{_to_iso('с.начало')} <= strftime('%Y-%m-%d','now','localtime','+6 days')",
    ]
    params = []

    if date_f:
        conditions.append("substr(с.начало,1,10) = ?")
        params.append(date_f)
    if genre_f:
        conditions.append("ф.жанр = ?")
        params.append(genre_f)
    if fmt_f:
        conditions.append("с.формат = ?")
        params.append(fmt_f)

    where = "WHERE " + " AND ".join(conditions)
    rows = db.execute(f"""
        SELECT с.код_сеанса, substr(с.начало,1,10) AS дата,
               ф.название AS фильм, ф.жанр, ф.возрастной_рейтинг, ф.длительность_мин,
               з.название AS зал, с.начало, с.окончание, с.формат, с.цена_руб
        FROM сеансы с
        JOIN фильмы ф ON ф.код_фильма=с.код_фильма
        JOIN залы   з ON з.код_зала=с.код_зала
        {where}
        ORDER BY {_to_iso('с.начало')}
    """, params).fetchall()

    from collections import OrderedDict
    by_date = OrderedDict()
    for r in rows:
        by_date.setdefault(r["дата"], []).append(r)

    genres  = [r[0] for r in db.execute("SELECT DISTINCT жанр FROM фильмы ORDER BY жанр").fetchall()]
    formats = ["2D", "3D", "IMAX", "4DX"]
    today_str = datetime.now().strftime("%d.%m.%Y")

    return render_template("schedule.html", by_date=by_date, genres=genres,
                           formats=formats, now_str=today_str,
                           date_f=date_f, genre_f=genre_f, fmt_f=fmt_f)


@app.route("/sessions/add", methods=["GET", "POST"])
@login_required
@role_required("администратор", "менеджер")
def session_add():
    db = get_db()
    if request.method == "POST":
        db.execute("""
            INSERT INTO сеансы (код_фильма,код_зала,начало,окончание,цена_руб,формат)
            VALUES (?,?,?,?,?,?)
        """, (
            int(request.form["код_фильма"]),
            int(request.form["код_зала"]),
            request.form["начало"].strip(),
            request.form["окончание"].strip(),
            float(request.form["цена_руб"]),
            request.form["формат"],
        ))
        db.commit()
        flash("Сеанс добавлен.", "success")
        return redirect(url_for("schedule"))
    films = db.execute("SELECT код_фильма, название FROM фильмы ORDER BY название").fetchall()
    halls = db.execute("SELECT код_зала, название FROM залы WHERE активен=1 ORDER BY код_зала").fetchall()
    return render_template("session_form.html", ses=None, action="add",
                           films=films, halls=halls)


@app.route("/sessions/<int:sid>/edit", methods=["GET", "POST"])
@login_required
@role_required("администратор", "менеджер")
def session_edit(sid):
    db = get_db()
    ses = db.execute("SELECT * FROM сеансы WHERE код_сеанса=?", (sid,)).fetchone()
    if not ses:
        flash("Сеанс не найден.", "danger")
        return redirect(url_for("schedule"))
    if request.method == "POST":
        db.execute("""
            UPDATE сеансы SET код_фильма=?,код_зала=?,начало=?,окончание=?,цена_руб=?,формат=?
            WHERE код_сеанса=?
        """, (
            int(request.form["код_фильма"]),
            int(request.form["код_зала"]),
            request.form["начало"].strip(),
            request.form["окончание"].strip(),
            float(request.form["цена_руб"]),
            request.form["формат"],
            sid,
        ))
        db.commit()
        flash("Сеанс обновлён.", "success")
        return redirect(url_for("schedule"))
    films = db.execute("SELECT код_фильма, название FROM фильмы ORDER BY название").fetchall()
    halls = db.execute("SELECT код_зала, название FROM залы WHERE активен=1 ORDER BY код_зала").fetchall()
    return render_template("session_form.html", ses=ses, action="edit",
                           films=films, halls=halls)


@app.route("/sessions/<int:sid>/delete", methods=["POST"])
@login_required
@role_required("администратор")
def session_delete(sid):
    db = get_db()
    db.execute("DELETE FROM сеансы WHERE код_сеанса=?", (sid,))
    db.commit()
    flash("Сеанс удалён.", "info")
    return redirect(url_for("schedule"))


# ── Билеты ────────────────────────────────────────────────────────────────────
@app.route("/tickets")
@login_required
def tickets():
    db = get_db()
    status_f = request.args.get("status", "")
    q        = request.args.get("q", "").strip()

    cond, params = [], []
    if status_f:
        cond.append("б.статус = ?")
        params.append(status_f)
    if q:
        cond.append("(к.полное_имя LIKE ? OR к.телефон LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]

    where = ("WHERE " + " AND ".join(cond)) if cond else ""
    rows = db.execute(f"""
        SELECT б.*, ф.название AS фильм, с.начало, з.название AS зал,
               м.ряд, м.номер_места, к.полное_имя AS клиент, к.телефон
        FROM билеты б
        JOIN сеансы с ON с.код_сеанса=б.код_сеанса
        JOIN фильмы ф ON ф.код_фильма=с.код_фильма
        JOIN залы   з ON з.код_зала=с.код_зала
        JOIN места  м ON м.код_места=б.код_места
        LEFT JOIN клиенты к ON к.код_клиента=б.код_клиента
        {where}
        ORDER BY б.код_билета DESC
        LIMIT 200
    """, params).fetchall()

    return render_template("tickets.html", tickets=rows,
                           status_f=status_f, q=q)


@app.route("/tickets/sell", methods=["GET", "POST"])
@login_required
@role_required("администратор", "менеджер", "кассир")
def ticket_sell():
    db = get_db()
    if request.method == "POST":
        sid      = int(request.form["код_сеанса"])
        seat_id  = int(request.form["код_места"])
        client_id = request.form.get("код_клиента") or None
        if client_id:
            client_id = int(client_id)
        price    = float(request.form["цена_руб"])
        payment  = request.form.get("способ_оплаты") or None
        status   = request.form.get("статус", "оплачен")
        now_str  = datetime.now().strftime("%d.%m.%Y %H:%M")
        try:
            db.execute("""
                INSERT INTO билеты (код_сеанса,код_места,код_клиента,цена_руб,статус,дата_покупки,способ_оплаты)
                VALUES (?,?,?,?,?,?,?)
            """, (sid, seat_id, client_id, price, status, now_str, payment))
            db.commit()
            flash("Билет оформлен.", "success")
            return redirect(url_for("tickets"))
        except sqlite3.IntegrityError:
            flash("Это место на данный сеанс уже занято.", "danger")

    sessions = db.execute("""
        SELECT с.код_сеанса, ф.название||' — '||с.начало AS label, с.цена_руб
        FROM сеансы с JOIN фильмы ф ON ф.код_фильма=с.код_фильма
        ORDER BY {iso} DESC
    """.format(iso=_to_iso("с.начало"))).fetchall()
    clients = db.execute("SELECT код_клиента, полное_имя, телефон FROM клиенты ORDER BY полное_имя").fetchall()
    # Свободные места (для первого сеанса по умолчанию)
    first_sid = sessions[0]["код_сеанса"] if sessions else None
    free_seats = _free_seats(db, first_sid) if first_sid else []

    return render_template("ticket_sell.html", sessions=sessions,
                           clients=clients, free_seats=free_seats)


@app.route("/tickets/free_seats/<int:sid>")
@login_required
def free_seats_api(sid):
    """JSON-like список свободных мест для AJAX."""
    from flask import jsonify
    db = get_db()
    seats = _free_seats(db, sid)
    ses = db.execute("SELECT цена_руб FROM сеансы WHERE код_сеанса=?", (sid,)).fetchone()
    return {"seats": [dict(s) for s in seats],
            "price": ses["цена_руб"] if ses else 0}


def _free_seats(db, sid):
    return db.execute("""
        SELECT м.код_места, м.ряд, м.номер_места, м.тип_места
        FROM места м
        JOIN сеансы с ON с.код_зала=м.код_зала
        WHERE с.код_сеанса=?
          AND м.код_места NOT IN (
              SELECT код_места FROM билеты
              WHERE код_сеанса=? AND статус NOT IN ('отменён')
          )
        ORDER BY м.ряд, м.номер_места
    """, (sid, sid)).fetchall()


@app.route("/tickets/<int:tid>/status", methods=["POST"])
@login_required
@role_required("администратор", "менеджер", "кассир")
def ticket_status(tid):
    new_status = request.form.get("статус")
    allowed = ("забронирован", "оплачен", "отменён", "использован")
    if new_status not in allowed:
        flash("Недопустимый статус.", "danger")
    else:
        db = get_db()
        db.execute("UPDATE билеты SET статус=? WHERE код_билета=?", (new_status, tid))
        db.commit()
        flash(f"Статус изменён на «{new_status}».", "success")
    return redirect(request.referrer or url_for("tickets"))


@app.route("/tickets/<int:tid>/delete", methods=["POST"])
@login_required
@role_required("администратор")
def ticket_delete(tid):
    db = get_db()
    db.execute("DELETE FROM билеты WHERE код_билета=?", (tid,))
    db.commit()
    flash("Билет удалён.", "info")
    return redirect(url_for("tickets"))


# ── Клиенты ───────────────────────────────────────────────────────────────────
@app.route("/clients")
@login_required
def clients():
    db = get_db()
    q = request.args.get("q", "").strip()
    if q:
        rows = db.execute("""
            SELECT к.*, COUNT(б.код_билета) AS билетов
            FROM клиенты к LEFT JOIN билеты б ON б.код_клиента=к.код_клиента
            WHERE к.полное_имя LIKE ? OR к.телефон LIKE ? OR к.электронная_почта LIKE ?
            GROUP BY к.код_клиента ORDER BY к.полное_имя
        """, (f"%{q}%", f"%{q}%", f"%{q}%")).fetchall()
    else:
        rows = db.execute("""
            SELECT к.*, COUNT(б.код_билета) AS билетов
            FROM клиенты к LEFT JOIN билеты б ON б.код_клиента=к.код_клиента
            GROUP BY к.код_клиента ORDER BY к.полное_имя
        """).fetchall()
    return render_template("clients.html", clients=rows, q=q)


@app.route("/clients/<int:cid>")
@login_required
def client_detail(cid):
    db = get_db()
    client = db.execute("SELECT * FROM клиенты WHERE код_клиента=?", (cid,)).fetchone()
    if not client:
        flash("Клиент не найден.", "danger")
        return redirect(url_for("clients"))
    history = db.execute("""
        SELECT б.*, ф.название AS фильм, с.начало, з.название AS зал,
               м.ряд, м.номер_места
        FROM билеты б
        JOIN сеансы с ON с.код_сеанса=б.код_сеанса
        JOIN фильмы ф ON ф.код_фильма=с.код_фильма
        JOIN залы   з ON з.код_зала=с.код_зала
        JOIN места  м ON м.код_места=б.код_места
        WHERE б.код_клиента=?
        ORDER BY б.дата_покупки DESC
    """, (cid,)).fetchall()
    return render_template("client_detail.html", client=client, history=history)


@app.route("/clients/add", methods=["GET", "POST"])
@login_required
@role_required("администратор", "менеджер", "кассир")
def client_add():
    if request.method == "POST":
        db = get_db()
        try:
            db.execute("""
                INSERT INTO клиенты (полное_имя,электронная_почта,телефон,бонусные_баллы,дата_регистрации)
                VALUES (?,?,?,?,?)
            """, (
                request.form["полное_имя"].strip(),
                request.form.get("электронная_почта", "").strip() or None,
                request.form.get("телефон", "").strip() or None,
                int(request.form.get("бонусные_баллы", 0)),
                datetime.now().strftime("%d.%m.%Y"),
            ))
            db.commit()
            flash("Клиент добавлен.", "success")
            return redirect(url_for("clients"))
        except sqlite3.IntegrityError:
            flash("Клиент с такой почтой уже существует.", "danger")
    return render_template("client_form.html", client=None, action="add")


@app.route("/clients/<int:cid>/edit", methods=["GET", "POST"])
@login_required
@role_required("администратор", "менеджер", "кассир")
def client_edit(cid):
    db = get_db()
    client = db.execute("SELECT * FROM клиенты WHERE код_клиента=?", (cid,)).fetchone()
    if not client:
        flash("Клиент не найден.", "danger")
        return redirect(url_for("clients"))
    if request.method == "POST":
        try:
            db.execute("""
                UPDATE клиенты SET полное_имя=?,электронная_почта=?,телефон=?,бонусные_баллы=?
                WHERE код_клиента=?
            """, (
                request.form["полное_имя"].strip(),
                request.form.get("электронная_почта", "").strip() or None,
                request.form.get("телефон", "").strip() or None,
                int(request.form.get("бонусные_баллы", 0)),
                cid,
            ))
            db.commit()
            flash("Клиент обновлён.", "success")
            return redirect(url_for("client_detail", cid=cid))
        except sqlite3.IntegrityError:
            flash("Клиент с такой почтой уже существует.", "danger")
    return render_template("client_form.html", client=client, action="edit")


@app.route("/clients/<int:cid>/delete", methods=["POST"])
@login_required
@role_required("администратор")
def client_delete(cid):
    db = get_db()
    db.execute("DELETE FROM клиенты WHERE код_клиента=?", (cid,))
    db.commit()
    flash("Клиент удалён.", "info")
    return redirect(url_for("clients"))


# ── Залы ──────────────────────────────────────────────────────────────────────
@app.route("/halls")
@login_required
def halls():
    db = get_db()
    rows = db.execute("""
        SELECT з.*,
               COUNT(DISTINCT с.код_сеанса) AS сеансов_всего,
               COUNT(б.код_билета) AS билетов_продано,
               ROUND(100.0*COUNT(б.код_билета)/NULLIF(з.вместимость*COUNT(DISTINCT с.код_сеанса),0),1) AS заполняемость
        FROM залы з
        LEFT JOIN сеансы с ON с.код_зала=з.код_зала
        LEFT JOIN билеты б ON б.код_сеанса=с.код_сеанса AND б.статус IN('оплачен','использован')
        GROUP BY з.код_зала ORDER BY з.код_зала
    """).fetchall()
    return render_template("halls.html", halls=rows)


# ── Статистика ────────────────────────────────────────────────────────────────
@app.route("/stats")
@login_required
def stats():
    db = get_db()
    top_films = db.execute("""
        SELECT ф.название, ф.жанр, COUNT(с.код_сеанса) AS сеансов
        FROM фильмы ф JOIN сеансы с ON с.код_фильма=ф.код_фильма
        GROUP BY ф.код_фильма ORDER BY сеансов DESC LIMIT 6
    """).fetchall()
    tickets_by_status = db.execute("""
        SELECT статус, COUNT(*) AS кол_во FROM билеты GROUP BY статус
    """).fetchall()
    revenue_by_hall = db.execute("""
        SELECT з.название AS зал, SUM(б.цена_руб) AS выручка
        FROM билеты б JOIN сеансы с ON с.код_сеанса=б.код_сеанса
        JOIN залы з ON з.код_зала=с.код_зала
        WHERE б.статус IN('оплачен','использован')
        GROUP BY з.код_зала ORDER BY выручка DESC
    """).fetchall()
    total_revenue = db.execute(
        "SELECT SUM(цена_руб) FROM билеты WHERE статус IN('оплачен','использован')"
    ).fetchone()[0] or 0
    total_tickets = db.execute("SELECT COUNT(*) FROM билеты").fetchone()[0]
    total_clients = db.execute("SELECT COUNT(*) FROM клиенты").fetchone()[0]
    total_films   = db.execute("SELECT COUNT(*) FROM фильмы").fetchone()[0]
    return render_template("stats.html", top_films=top_films,
                           tickets_by_status=tickets_by_status,
                           revenue_by_hall=revenue_by_hall,
                           total_revenue=total_revenue,
                           total_tickets=total_tickets,
                           total_clients=total_clients,
                           total_films=total_films)


if __name__ == "__main__":
    if not os.path.exists(DB_NAME):
        print(f"ОШИБКА: база данных '{DB_NAME}' не найдена.")
        print("Сначала запустите: python main.py && python seed.py")
    else:
        app.run(debug=True)
