from flask import Flask, render_template, request, redirect, url_for, session, flash
from datetime import datetime, date, timedelta
import sqlite3
import os
import hashlib

app = Flask(__name__)
app.secret_key = 'kinomax_secret_key_2026'
DB_PATH = 'kinomax.db'


# ─────────────────────────────────────────────
# БД: создание и заполнение
# ─────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

    c.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'client'
        );

        CREATE TABLE IF NOT EXISTS films (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            genre TEXT,
            duration INTEGER,
            poster TEXT
        );

        CREATE TABLE IF NOT EXISTS halls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            capacity INTEGER NOT NULL,
            rows INTEGER NOT NULL,
            seats_per_row INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            film_id INTEGER NOT NULL,
            hall_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            price REAL NOT NULL,
            FOREIGN KEY (film_id) REFERENCES films(id),
            FOREIGN KEY (hall_id) REFERENCES halls(id)
        );

        CREATE TABLE IF NOT EXISTS seats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hall_id INTEGER NOT NULL,
            row_num INTEGER NOT NULL,
            seat_num INTEGER NOT NULL,
            FOREIGN KEY (hall_id) REFERENCES halls(id)
        );

        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            session_id INTEGER NOT NULL,
            seat_id INTEGER NOT NULL,
            booked_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (session_id) REFERENCES sessions(id),
            FOREIGN KEY (seat_id) REFERENCES seats(id)
        );
    ''')

    conn.commit()
    seed_db(conn)
    conn.close()


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def seed_db(conn):
    c = conn.cursor()

    # Проверяем — уже заполнено?
    if c.execute('SELECT COUNT(*) FROM users').fetchone()[0] > 0:
        return

    # Пользователи
    users = [
        ('Администратор', 'admin@kinomax.ru', hash_password('admin123'), 'admin'),
        ('Иван Петров', 'ivan@mail.ru', hash_password('ivan123'), 'client'),
        ('Мария Сидорова', 'maria@mail.ru', hash_password('maria123'), 'client'),
        ('Алексей Козлов', 'alexey@mail.ru', hash_password('alex123'), 'client'),
    ]
    c.executemany('INSERT INTO users (name, email, password, role) VALUES (?,?,?,?)', users)

    # Фильмы
    films = [
        ('Мастер и Маргарита', 'Экранизация культового романа Булгакова. История о визите таинственного Воланда в советскую Москву.', 'Драма / Фэнтези', 144, 'master.jpg'),
        ('Чебурашка', 'Добрая история о маленьком существе, которое ищет своё место в мире и настоящих друзей.', 'Семейный', 112, 'cheburashka.jpg'),
        ('Сто лет тому вперёд', 'Фантастическое приключение о путешествии во времени, основанное на повести Кира Булычёва.', 'Фантастика / Приключения', 130, 'future.jpg'),
        ('Холоп 2', 'Продолжение комедии о мажоре, которого снова отправляют на перевоспитание в прошлое.', 'Комедия', 118, 'holop.jpg'),
        ('Лёд 3', 'Финальная часть трилогии о фигурном катании, любви и больших мечтах.', 'Мелодрама / Спорт', 125, 'ice.jpg'),
    ]
    c.executemany('INSERT INTO films (title, description, genre, duration, poster) VALUES (?,?,?,?,?)', films)

    # Залы
    halls = [
        ('Красный зал', 60, 6, 10),
        ('Синий зал', 80, 8, 10),
        ('VIP-зал', 30, 5, 6),
    ]
    c.executemany('INSERT INTO halls (name, capacity, rows, seats_per_row) VALUES (?,?,?,?)', halls)

    conn.commit()

    # Места для каждого зала
    for hall in c.execute('SELECT id, rows, seats_per_row FROM halls').fetchall():
        for row in range(1, hall['rows'] + 1):
            for seat in range(1, hall['seats_per_row'] + 1):
                c.execute('INSERT INTO seats (hall_id, row_num, seat_num) VALUES (?,?,?)',
                          (hall['id'], row, seat))

    conn.commit()

    # Сеансы на ближайшие 7 дней
    today = date.today()
    session_data = []
    times = ['10:00', '13:30', '16:00', '19:30', '22:00']
    prices = [350, 350, 400, 450, 400]

    film_ids = [r['id'] for r in c.execute('SELECT id FROM films').fetchall()]
    hall_ids = [r['id'] for r in c.execute('SELECT id FROM halls').fetchall()]

    import random
    random.seed(42)
    for day_offset in range(7):
        d = (today + timedelta(days=day_offset)).isoformat()
        for i, (t, p) in enumerate(zip(times, prices)):
            film_id = film_ids[random.randint(0, len(film_ids) - 1)]
            hall_id = hall_ids[random.randint(0, len(hall_ids) - 1)]
            session_data.append((film_id, hall_id, d, t, p))

    c.executemany('INSERT INTO sessions (film_id, hall_id, date, time, price) VALUES (?,?,?,?,?)', session_data)

    # Несколько тестовых бронирований
    sessions_list = c.execute('SELECT id, hall_id FROM sessions LIMIT 3').fetchall()
    client_id = c.execute("SELECT id FROM users WHERE role='client' LIMIT 1").fetchone()['id']
    now = datetime.now().isoformat()

    for sess in sessions_list:
        seat = c.execute('SELECT id FROM seats WHERE hall_id=? LIMIT 1', (sess['hall_id'],)).fetchone()
        if seat:
            c.execute('INSERT INTO bookings (user_id, session_id, seat_id, booked_at) VALUES (?,?,?,?)',
                      (client_id, sess['id'], seat['id'], now))

    conn.commit()


# ─────────────────────────────────────────────
# Вспомогательные функции
# ─────────────────────────────────────────────

def current_user():
    if 'user_id' in session:
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone()
        conn.close()
        return user
    return None


def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Войдите в систему', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        user = current_user()
        if not user or user['role'] != 'admin':
            flash('Доступ запрещён', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated


# ─────────────────────────────────────────────
# ПУБЛИЧНАЯ ЧАСТЬ
# ─────────────────────────────────────────────

@app.route('/')
def index():
    conn = get_db()
    films = conn.execute('SELECT * FROM films').fetchall()
    today = date.today().isoformat()
    # Ближайшие сеансы сегодня
    upcoming = conn.execute('''
        SELECT s.*, f.title, h.name as hall_name
        FROM sessions s
        JOIN films f ON s.film_id = f.id
        JOIN halls h ON s.hall_id = h.id
        WHERE s.date = ?
        ORDER BY s.time
    ''', (today,)).fetchall()
    conn.close()
    return render_template('index.html', films=films, upcoming=upcoming, user=current_user())


@app.route('/film/<int:film_id>')
def film(film_id):
    conn = get_db()
    f = conn.execute('SELECT * FROM films WHERE id=?', (film_id,)).fetchone()
    if not f:
        conn.close()
        return redirect(url_for('index'))
    today = date.today().isoformat()
    sessions = conn.execute('''
        SELECT s.*, h.name as hall_name
        FROM sessions s
        JOIN halls h ON s.hall_id = h.id
        WHERE s.film_id=? AND s.date >= ?
        ORDER BY s.date, s.time
    ''', (film_id, today)).fetchall()
    conn.close()
    return render_template('film.html', film=f, sessions=sessions, user=current_user())


@app.route('/session/<int:session_id>')
@login_required
def session_view(session_id):
    conn = get_db()
    sess = conn.execute('''
        SELECT s.*, f.title, f.duration, h.name as hall_name, h.rows, h.seats_per_row
        FROM sessions s
        JOIN films f ON s.film_id = f.id
        JOIN halls h ON s.hall_id = h.id
        WHERE s.id=?
    ''', (session_id,)).fetchone()
    if not sess:
        conn.close()
        return redirect(url_for('index'))

    # Занятые места
    booked_seat_ids = [r['seat_id'] for r in
                       conn.execute('SELECT seat_id FROM bookings WHERE session_id=?', (session_id,)).fetchall()]

    # Все места зала
    seats = conn.execute('SELECT * FROM seats WHERE hall_id=? ORDER BY row_num, seat_num',
                         (sess['hall_id'],)).fetchall()
    conn.close()

    # Группируем по рядам
    rows = {}
    for seat in seats:
        r = seat['row_num']
        if r not in rows:
            rows[r] = []
        rows[r].append({'id': seat['id'], 'num': seat['seat_num'],
                        'booked': seat['id'] in booked_seat_ids})

    return render_template('session.html', sess=sess, rows=rows, user=current_user())


@app.route('/book', methods=['POST'])
@login_required
def book():
    session_id = request.form.get('session_id', type=int)
    seat_id = request.form.get('seat_id', type=int)
    user = current_user()

    conn = get_db()
    # Проверяем, не занято ли уже
    existing = conn.execute('SELECT id FROM bookings WHERE session_id=? AND seat_id=?',
                            (session_id, seat_id)).fetchone()
    if existing:
        flash('Это место уже занято. Выберите другое.', 'danger')
        conn.close()
        return redirect(url_for('session_view', session_id=session_id))

    conn.execute('INSERT INTO bookings (user_id, session_id, seat_id, booked_at) VALUES (?,?,?,?)',
                 (user['id'], session_id, seat_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    flash('Бронирование успешно оформлено!', 'success')
    return redirect(url_for('cabinet'))


@app.route('/cabinet')
@login_required
def cabinet():
    user = current_user()
    conn = get_db()
    bookings = conn.execute('''
        SELECT b.*, f.title, s.date, s.time, h.name as hall_name,
               se.row_num, se.seat_num, s.price
        FROM bookings b
        JOIN sessions s ON b.session_id = s.id
        JOIN films f ON s.film_id = f.id
        JOIN halls h ON s.hall_id = h.id
        JOIN seats se ON b.seat_id = se.id
        WHERE b.user_id=?
        ORDER BY s.date DESC, s.time DESC
    ''', (user['id'],)).fetchall()
    conn.close()
    return render_template('cabinet.html', user=user, bookings=bookings)


@app.route('/cancel_booking/<int:booking_id>', methods=['POST'])
@login_required
def cancel_booking(booking_id):
    user = current_user()
    conn = get_db()
    booking = conn.execute('SELECT * FROM bookings WHERE id=? AND user_id=?',
                           (booking_id, user['id'])).fetchone()
    if booking:
        conn.execute('DELETE FROM bookings WHERE id=?', (booking_id,))
        conn.commit()
        flash('Бронирование отменено.', 'info')
    conn.close()
    return redirect(url_for('cabinet'))


# ─────────────────────────────────────────────
# АВТОРИЗАЦИЯ
# ─────────────────────────────────────────────

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name'].strip()
        email = request.form['email'].strip().lower()
        password = request.form['password']
        conn = get_db()
        existing = conn.execute('SELECT id FROM users WHERE email=?', (email,)).fetchone()
        if existing:
            flash('Пользователь с таким email уже существует.', 'danger')
            conn.close()
            return render_template('register.html', user=None)
        conn.execute('INSERT INTO users (name, email, password, role) VALUES (?,?,?,?)',
                     (name, email, hash_password(password), 'client'))
        conn.commit()
        user = conn.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
        session['user_id'] = user['id']
        conn.close()
        flash(f'Добро пожаловать, {name}!', 'success')
        return redirect(url_for('index'))
    return render_template('register.html', user=current_user())


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE email=? AND password=?',
                            (email, hash_password(password))).fetchone()
        conn.close()
        if user:
            session['user_id'] = user['id']
            flash(f'Добро пожаловать, {user["name"]}!', 'success')
            return redirect(url_for('index'))
        flash('Неверный email или пароль.', 'danger')
    return render_template('login.html', user=current_user())


@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы.', 'info')
    return redirect(url_for('index'))


# ─────────────────────────────────────────────
# АДМИН-ПАНЕЛЬ
# ─────────────────────────────────────────────

@app.route('/admin')
@admin_required
def admin():
    conn = get_db()
    stats = {
        'films': conn.execute('SELECT COUNT(*) as c FROM films').fetchone()['c'],
        'halls': conn.execute('SELECT COUNT(*) as c FROM halls').fetchone()['c'],
        'sessions': conn.execute('SELECT COUNT(*) as c FROM sessions').fetchone()['c'],
        'bookings': conn.execute('SELECT COUNT(*) as c FROM bookings').fetchone()['c'],
        'users': conn.execute("SELECT COUNT(*) as c FROM users WHERE role='client'").fetchone()['c'],
    }
    conn.close()
    return render_template('admin/index.html', user=current_user(), stats=stats)


# --- Фильмы ---
@app.route('/admin/films')
@admin_required
def admin_films():
    conn = get_db()
    films = conn.execute('SELECT * FROM films').fetchall()
    conn.close()
    return render_template('admin/films.html', films=films, user=current_user())


@app.route('/admin/films/add', methods=['GET', 'POST'])
@admin_required
def admin_film_add():
    if request.method == 'POST':
        title = request.form['title'].strip()
        description = request.form['description'].strip()
        genre = request.form['genre'].strip()
        duration = request.form['duration']
        poster = request.form['poster'].strip()
        conn = get_db()
        conn.execute('INSERT INTO films (title, description, genre, duration, poster) VALUES (?,?,?,?,?)',
                     (title, description, genre, duration, poster))
        conn.commit()
        conn.close()
        flash('Фильм добавлен.', 'success')
        return redirect(url_for('admin_films'))
    return render_template('admin/film_form.html', film=None, user=current_user())


@app.route('/admin/films/edit/<int:film_id>', methods=['GET', 'POST'])
@admin_required
def admin_film_edit(film_id):
    conn = get_db()
    film = conn.execute('SELECT * FROM films WHERE id=?', (film_id,)).fetchone()
    if request.method == 'POST':
        title = request.form['title'].strip()
        description = request.form['description'].strip()
        genre = request.form['genre'].strip()
        duration = request.form['duration']
        poster = request.form['poster'].strip()
        conn.execute('UPDATE films SET title=?, description=?, genre=?, duration=?, poster=? WHERE id=?',
                     (title, description, genre, duration, poster, film_id))
        conn.commit()
        conn.close()
        flash('Фильм обновлён.', 'success')
        return redirect(url_for('admin_films'))
    conn.close()
    return render_template('admin/film_form.html', film=film, user=current_user())


@app.route('/admin/films/delete/<int:film_id>', methods=['POST'])
@admin_required
def admin_film_delete(film_id):
    conn = get_db()
    conn.execute('DELETE FROM films WHERE id=?', (film_id,))
    conn.commit()
    conn.close()
    flash('Фильм удалён.', 'info')
    return redirect(url_for('admin_films'))


# --- Залы ---
@app.route('/admin/halls')
@admin_required
def admin_halls():
    conn = get_db()
    halls = conn.execute('SELECT * FROM halls').fetchall()
    conn.close()
    return render_template('admin/halls.html', halls=halls, user=current_user())


@app.route('/admin/halls/add', methods=['GET', 'POST'])
@admin_required
def admin_hall_add():
    if request.method == 'POST':
        name = request.form['name'].strip()
        rows = int(request.form['rows'])
        seats_per_row = int(request.form['seats_per_row'])
        capacity = rows * seats_per_row
        conn = get_db()
        conn.execute('INSERT INTO halls (name, capacity, rows, seats_per_row) VALUES (?,?,?,?)',
                     (name, capacity, rows, seats_per_row))
        hall_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        for row in range(1, rows + 1):
            for seat in range(1, seats_per_row + 1):
                conn.execute('INSERT INTO seats (hall_id, row_num, seat_num) VALUES (?,?,?)',
                             (hall_id, row, seat))
        conn.commit()
        conn.close()
        flash('Зал добавлен.', 'success')
        return redirect(url_for('admin_halls'))
    return render_template('admin/hall_form.html', hall=None, user=current_user())


@app.route('/admin/halls/delete/<int:hall_id>', methods=['POST'])
@admin_required
def admin_hall_delete(hall_id):
    conn = get_db()
    conn.execute('DELETE FROM halls WHERE id=?', (hall_id,))
    conn.execute('DELETE FROM seats WHERE hall_id=?', (hall_id,))
    conn.commit()
    conn.close()
    flash('Зал удалён.', 'info')
    return redirect(url_for('admin_halls'))


# --- Сеансы ---
@app.route('/admin/sessions')
@admin_required
def admin_sessions():
    conn = get_db()
    sessions = conn.execute('''
        SELECT s.*, f.title, h.name as hall_name
        FROM sessions s
        JOIN films f ON s.film_id = f.id
        JOIN halls h ON s.hall_id = h.id
        ORDER BY s.date, s.time
    ''').fetchall()
    conn.close()
    return render_template('admin/sessions.html', sessions=sessions, user=current_user())


@app.route('/admin/sessions/add', methods=['GET', 'POST'])
@admin_required
def admin_session_add():
    conn = get_db()
    if request.method == 'POST':
        film_id = request.form['film_id']
        hall_id = request.form['hall_id']
        date_val = request.form['date']
        time_val = request.form['time']
        price = request.form['price']
        conn.execute('INSERT INTO sessions (film_id, hall_id, date, time, price) VALUES (?,?,?,?,?)',
                     (film_id, hall_id, date_val, time_val, price))
        conn.commit()
        conn.close()
        flash('Сеанс добавлен.', 'success')
        return redirect(url_for('admin_sessions'))
    films = conn.execute('SELECT * FROM films').fetchall()
    halls = conn.execute('SELECT * FROM halls').fetchall()
    conn.close()
    return render_template('admin/session_form.html', films=films, halls=halls, sess=None, user=current_user())


@app.route('/admin/sessions/delete/<int:session_id>', methods=['POST'])
@admin_required
def admin_session_delete(session_id):
    conn = get_db()
    conn.execute('DELETE FROM sessions WHERE id=?', (session_id,))
    conn.commit()
    conn.close()
    flash('Сеанс удалён.', 'info')
    return redirect(url_for('admin_sessions'))


# --- Бронирования ---
@app.route('/admin/bookings')
@admin_required
def admin_bookings():
    conn = get_db()
    filter_date = request.args.get('date', '')
    filter_film = request.args.get('film_id', '')
    query = '''
        SELECT b.*, u.name as user_name, u.email, f.title, s.date, s.time,
               h.name as hall_name, se.row_num, se.seat_num, s.price
        FROM bookings b
        JOIN users u ON b.user_id = u.id
        JOIN sessions s ON b.session_id = s.id
        JOIN films f ON s.film_id = f.id
        JOIN halls h ON s.hall_id = h.id
        JOIN seats se ON b.seat_id = se.id
        WHERE 1=1
    '''
    params = []
    if filter_date:
        query += ' AND s.date=?'
        params.append(filter_date)
    if filter_film:
        query += ' AND s.film_id=?'
        params.append(filter_film)
    query += ' ORDER BY s.date DESC, s.time DESC'
    bookings = conn.execute(query, params).fetchall()
    films = conn.execute('SELECT * FROM films').fetchall()
    conn.close()
    return render_template('admin/bookings.html', bookings=bookings, films=films,
                           filter_date=filter_date, filter_film=filter_film, user=current_user())


# --- Пользователи ---
@app.route('/admin/users')
@admin_required
def admin_users():
    conn = get_db()
    users = conn.execute('SELECT id, name, email, role FROM users ORDER BY id').fetchall()
    conn.close()
    return render_template('admin/users.html', users=users, user=current_user())


@app.route('/admin/users/delete/<int:user_id>', methods=['POST'])
@admin_required
def admin_user_delete(user_id):
    user = current_user()
    if user['id'] == user_id:
        flash('Нельзя удалить собственный аккаунт.', 'danger')
        return redirect(url_for('admin_users'))
    conn = get_db()
    conn.execute('DELETE FROM users WHERE id=?', (user_id,))
    conn.commit()
    conn.close()
    flash('Пользователь удалён.', 'info')
    return redirect(url_for('admin_users'))


# ─────────────────────────────────────────────
if __name__ == '__main__':
    init_db()
    app.run(debug=True)