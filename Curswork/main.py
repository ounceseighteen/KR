from flask import Flask, render_template, request, redirect, url_for, session, flash
from datetime import datetime, date, timedelta
import sqlite3
import os
import hashlib
import re
from flask_mail import Mail, Message
import random
import time
import uuid

app = Flask(__name__)
app.secret_key = 'Mir_Kino_secret_key_2026'
DB_PATH = 'kinomax.db'
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'mirkino.auth@gmail.com'
app.config['MAIL_PASSWORD'] = 'zkho hewq vqdj czjl'
app.config['MAIL_DEFAULT_SENDER'] = ('Мир Кино', 'mirkino.auth@gmail.com')

mail = Mail(app)


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
            role TEXT NOT NULL DEFAULT 'client',
            is_banned INTEGER NOT NULL DEFAULT 0
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
            seats_per_row INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            format TEXT NOT NULL DEFAULT '2D'
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
            status TEXT NOT NULL DEFAULT 'booked',
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
        ('Кассир','cashier@Mirkino.ru', hash_password('cashier123'), 'cashier'),
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

def is_valid_email(email):
    # Регулярное выражение: проверяет структуру логин@домен.зона
    # Не пропускает адреса без точки, без собаки или с запрещенными символами
    email_regex = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
    return re.match(email_regex, email) is not None

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

@app.route('/verify_recovery_code', methods=['POST'])
def verify_recovery_code():
    input_code = request.form.get('code', '').strip()
    stored_code = session.get('recovery_code')

    stored_time = session.get('recovery_time')

    if not stored_code or not stored_time:
        return {"status": "error", "message": "Код не найден"}, 400

    if time.time() - stored_time > 300:  # 5 минут
        session.pop('recovery_code', None)
        session.pop('recovery_time', None)
        return {"status": "error", "message": "Код истёк. Запросите новый."}, 400

    if input_code == stored_code:
        return {"status": "success", "message": "Код подтвержден"}
    else:
        return {"status": "error", "message": "Неверный код"}, 400

@app.route('/reset_password', methods=['POST'])
def reset_password():
    new_password = request.form.get('password', '')
    email = session.get('recovery_email')

    if not email or not new_password:
        return {"status": "error", "message": "Сессия истекла или данные неполные"}, 400

    hashed_pw = hash_password(new_password)
    conn = get_db()
    conn.execute('UPDATE users SET password=? WHERE email=?', (hashed_pw, email))
    conn.commit()
    conn.close()

    session.pop('recovery_code', None)
    session.pop('recovery_email', None)

    # Возвращаем JSON, а не редирект!
    return {"status": "success", "message": "Пароль успешно изменен"}

@app.route('/')
def index():
    user = current_user()
    if user and user['role'] in ('admin', 'cashier'):
        return redirect(url_for('personal'))
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
    return render_template('user/index.html', films=films, upcoming=upcoming, user=current_user())


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
    return render_template('user/film.html', film=f, sessions=sessions, user=current_user())


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

    return render_template('user/session.html', sess=sess, rows=rows, user=current_user())


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

    conn.execute('INSERT INTO bookings (user_id, session_id, seat_id, booked_at, status) VALUES (?,?,?,?,?)',
                 (user['id'], session_id, seat_id, datetime.now().isoformat(), 'booked'))
    conn.commit()
    conn.close()
    flash('Бронирование успешно оформлено!', 'success')
    return redirect(url_for('cabinet'))


@app.route('/cabinet')
@login_required
def cabinet():
    user = current_user()
    if user['role'] in ('admin', 'cashier'):
        return redirect(url_for('personal'))
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
    return render_template('user/cabinet.html', user=user, bookings=bookings)

@app.route('/personal')
@login_required
def personal():
    user = current_user()
    if user['role'] == 'client':
        return redirect(url_for('index'))

    conn = get_db()
    data = {}
    data['today'] = date.today().isoformat()
    data['now_time'] = datetime.now().strftime('%H:%M')

    if user['role'] == 'admin':
        data['films'] = conn.execute('SELECT * FROM films ORDER BY id').fetchall()
        data['halls'] = conn.execute('SELECT * FROM halls ORDER BY id').fetchall()
        data['users'] = conn.execute('SELECT id, name, email, role, is_banned FROM users ORDER BY id').fetchall()
        data['stats'] = {
            'films': conn.execute('SELECT COUNT(*) as c FROM films').fetchone()['c'],
            'halls': conn.execute('SELECT COUNT(*) as c FROM halls').fetchone()['c'],
            'sessions': conn.execute('SELECT COUNT(*) as c FROM sessions').fetchone()['c'],
            'bookings': conn.execute('SELECT COUNT(*) as c FROM bookings').fetchone()['c'],
            'users': conn.execute("SELECT COUNT(*) as c FROM users WHERE role='client'").fetchone()['c'],
        }

    data['sessions'] = conn.execute('''
        SELECT s.*, f.title, h.name as hall_name,
               CASE WHEN s.date < ? OR (s.date = ? AND s.time < ?) THEN 1 ELSE 0 END as is_past
        FROM sessions s
        JOIN films f ON f.id = s.film_id
        JOIN halls h ON h.id = s.hall_id
        ORDER BY is_past ASC, s.date ASC, s.time ASC
    ''', (data['today'], data['today'], data['now_time'])).fetchall()

    data['bookings'] = conn.execute('''
        SELECT b.*, f.title, s.date, s.time, h.name as hall_name, u.name as user_name
        FROM bookings b
        JOIN sessions s ON s.id = b.session_id
        JOIN films f ON f.id = s.film_id
        JOIN halls h ON h.id = s.hall_id
        JOIN users u ON u.id = b.user_id
        ORDER BY s.date, s.time
    ''').fetchall()

    conn.close()
    return render_template('admin/personal.html', user=user, **data)

@app.route('/update_profile', methods=['POST'])
@login_required
def update_profile():
    user_id = session['user_id']
    new_name = request.form.get('name', '').strip()
    new_email = request.form.get('email', '').strip()

    conn = get_db()
    cursor = conn.cursor()

    if new_name:
        cursor.execute("UPDATE users SET name = ? WHERE id = ?", (new_name, user_id))
        session['user_name'] = new_name

    if new_email:
        # Проверка что email не занят
        existing = cursor.execute("SELECT id FROM users WHERE email = ? AND id != ?", (new_email, user_id)).fetchone()
        if existing:
            conn.close()
            return {"status": "error", "message": "Email уже занят"}, 400
        cursor.execute("UPDATE users SET email = ? WHERE id = ?", (new_email, user_id))

    conn.commit()
    conn.close()
    return {"status": "ok", "message": "Данные сохранены"}


@app.route('/update_password', methods=['POST'])
@login_required
def update_password():
    user_id = session['user_id']
    old_password = request.form.get('old_password', '').strip()
    new_password = request.form.get('new_password', '').strip()
    confirm_password = request.form.get('confirm_password', '').strip()

    if not old_password or not new_password or not confirm_password:
        return {"status": "error", "message": "Заполните все поля"}, 400

    if new_password != confirm_password:
        return {"status": "error", "message": "Пароли не совпадают"}, 400

    conn = get_db()
    user = conn.execute("SELECT password FROM users WHERE id = ?", (user_id,)).fetchone()

    if user['password'] != hash_password(old_password):
        conn.close()
        return {"status": "error", "message": "Неверный текущий пароль"}, 400

    conn.execute("UPDATE users SET password = ? WHERE id = ?", (hash_password(new_password), user_id))
    conn.commit()
    conn.close()
    return {"status": "ok", "message": "Пароль изменён"}

@app.route('/cancel_booking/<int:booking_id>', methods=['POST'])
@app.route('/cancel_booking/<int:booking_id>', methods=['POST'])
@login_required
def cancel_booking(booking_id):
    user = current_user()
    conn = get_db()

    # Админ/кассир может отменять любое бронирование, клиент — только своё
    if user['role'] in ('admin', 'cashier'):
        booking = conn.execute('SELECT * FROM bookings WHERE id=?', (booking_id,)).fetchone()
    else:
        booking = conn.execute('SELECT * FROM bookings WHERE id=? AND user_id=?',
                               (booking_id, user['id'])).fetchone()

    if booking:
        conn.execute("UPDATE bookings SET status='cancelled' WHERE id=?", (booking_id,))
        conn.commit()

    conn.close()

    # Редирект обратно туда откуда пришли
    if user['role'] in ('admin', 'cashier'):
        return redirect(url_for('personal') + '?tab=bookings')
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

        if not is_valid_email(email):
            flash('Некорректный формат почты. Пример: user@example.com', 'danger')
            return redirect(url_for('index'))

        confirm_password = request.form.get('confirm_password', '')
        if password != confirm_password:
            flash('Пароли не совпадают.', 'danger')
            return redirect(url_for('index'))
        conn = get_db()
        existing = conn.execute('SELECT id FROM users WHERE email=?', (email,)).fetchone()
        if existing:
            flash('Email уже зарегистрирован', 'danger')
            conn.close()
            return redirect(url_for('index'))
        conn.execute('INSERT INTO users (name, email, password, role) VALUES (?,?,?,?)',
                     (name, email, hash_password(password), 'client'))
        conn.commit()
        user = conn.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
        session['user_id'] = user['id']
        conn.close()
        flash(f'Добро пожаловать, {name}!', 'success')
        return redirect(url_for('index'))
    return redirect(url_for('index'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    email = request.form.get('email')
    password = request.form.get('password')

    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
    conn.close()

    if user and hashlib.sha256(password.encode()).hexdigest() == user['password']:
        if user['is_banned']:
            flash('Ваш аккаунт заблокирован.', 'danger')
            return redirect(url_for('index'))
        session['user_id'] = user['id']
        session['user_role'] = user['role']
        flash('Вы успешно вошли!', 'success')
        if user['role'] in ('admin', 'cashier'):
            return redirect(url_for('personal'))
        return redirect(url_for('index'))
    else:
        # Вместо текста ошибки перенаправляем обратно на главную
        flash('Неверный email или пароль', 'danger')
        return redirect(url_for('index'))


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

@app.route('/admin/films/poster/<int:film_id>', methods=['POST'])
@admin_required
def admin_film_poster(film_id):
    poster_file = request.files.get('poster')
    if poster_file and poster_file.filename:
        import os
        from werkzeug.utils import secure_filename
        ext = os.path.splitext(poster_file.filename)[1].lower()
        poster_filename = secure_filename(f"film_{uuid.uuid4().hex}{ext}")
        save_path = os.path.join('static', 'posters', poster_filename)
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        poster_file.save(save_path)
        conn = get_db()
        conn.execute('UPDATE films SET poster=? WHERE id=?', (poster_filename, film_id))
        conn.commit()
        conn.close()
    return redirect(url_for('personal') + '?tab=films')

@app.route('/admin/films/add', methods=['POST'])
@admin_required
def admin_film_add():
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    genre = request.form.get('genre', '').strip()
    duration = request.form.get('duration', '').strip()
    poster_file = request.files.get('poster')

    if not title or not duration:
        return redirect(url_for('personal') + '?tab=films')

    poster_filename = ''
    if poster_file and poster_file.filename:
        import os
        from werkzeug.utils import secure_filename
        ext = os.path.splitext(poster_file.filename)[1].lower()
        poster_filename = secure_filename(f"film_{uuid.uuid4().hex}{ext}")
        save_path = os.path.join('static', 'posters', poster_filename)
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        poster_file.save(save_path)

    conn = get_db()
    conn.execute('INSERT INTO films (title, description, genre, duration, poster) VALUES (?,?,?,?,?)',
                 (title, description, genre, int(duration), poster_filename))
    conn.commit()
    conn.close()
    return redirect(url_for('personal') + '?tab=films')


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
        return redirect(url_for('personal') + '?tab=films')
    conn.close()
    return render_template('admin/film_form.html', film=film, user=current_user())


@app.route('/admin/films/delete/<int:film_id>', methods=['POST'])
@admin_required
def admin_film_delete(film_id):
    conn = get_db()
    conn.execute('DELETE FROM films WHERE id=?', (film_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('personal') + '?tab=films')

@app.route('/admin/films/inline-edit/<int:film_id>', methods=['POST'])
@admin_required
def admin_film_inline_edit(film_id):
    title = request.form.get('title', '').strip()
    genre = request.form.get('genre', '').strip()
    duration = request.form.get('duration', '').strip()
    if not title or not duration:
        return redirect(url_for('personal') + '?tab=films')
    conn = get_db()
    conn.execute('UPDATE films SET title=?, genre=?, duration=? WHERE id=?',
                 (title, genre, int(duration), film_id))
    conn.commit()
    conn.close()
    return redirect(url_for('personal') + '?tab=films')


# --- Залы ---
@app.route('/admin/halls')
@admin_required
def admin_halls():
    conn = get_db()
    halls = conn.execute('SELECT * FROM halls').fetchall()
    conn.close()
    return render_template('admin/halls.html', halls=halls, user=current_user())


@app.route('/admin/halls/add', methods=['POST'])
@admin_required
def admin_hall_add():
    name = request.form.get('name', '').strip()
    rows = request.form.get('rows', '').strip()
    seats_per_row = request.form.get('seats_per_row', '').strip()
    format = request.form.get('format', '2D')

    if not name or not rows or not seats_per_row:
        return redirect(url_for('personal') + '?tab=halls')

    rows = int(rows)
    seats_per_row = int(seats_per_row)
    capacity = rows * seats_per_row

    conn = get_db()
    conn.execute('INSERT INTO halls (name, capacity, rows, seats_per_row, format) VALUES (?,?,?,?,?)',
                 (name, capacity, rows, seats_per_row, format))
    hall_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    for row in range(1, rows + 1):
        for seat in range(1, seats_per_row + 1):
            conn.execute('INSERT INTO seats (hall_id, row_num, seat_num) VALUES (?,?,?)',
                         (hall_id, row, seat))
    conn.commit()
    conn.close()
    return redirect(url_for('personal') + '?tab=halls')


@app.route('/admin/halls/delete/<int:hall_id>', methods=['POST'])
@admin_required
def admin_hall_delete(hall_id):
    conn = get_db()
    conn.execute('DELETE FROM halls WHERE id=?', (hall_id,))
    conn.execute('DELETE FROM seats WHERE hall_id=?', (hall_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('personal') + '?tab=halls')

@app.route('/admin/halls/edit/<int:hall_id>', methods=['POST'])
@admin_required
def admin_hall_edit(hall_id):
    name = request.form.get('name', '').strip()
    status = request.form.get('status', 'open')
    capacity = request.form.get('capacity', '').strip()
    format = request.form.get('format', '2D')
    if not name or not capacity:
        return redirect(url_for('personal') + '?tab=halls')
    conn = get_db()
    conn.execute('UPDATE halls SET name=?, status=?, capacity=?, format=? WHERE id=?',
                 (name, status, int(capacity), format, hall_id))
    conn.commit()
    conn.close()
    return redirect(url_for('personal') + '?tab=halls')


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


@app.route('/admin/sessions/add', methods=['POST'])
@admin_required
def admin_session_add():
    film_id = request.form.get('film_id')
    hall_id = request.form.get('hall_id')
    date = request.form.get('date')
    time = request.form.get('time')
    price = request.form.get('price')

    if not all([film_id, hall_id, date, time, price]):
        return redirect(url_for('personal') + '?tab=sessions')

    conn = get_db()
    conn.execute('INSERT INTO sessions (film_id, hall_id, date, time, price) VALUES (?,?,?,?,?)',
                 (film_id, hall_id, date, time, price))
    conn.commit()
    conn.close()
    return redirect(url_for('personal') + '?tab=sessions')


@app.route('/admin/sessions/delete/<int:session_id>', methods=['POST'])
@admin_required
def admin_session_delete(session_id):
    conn = get_db()
    conn.execute('DELETE FROM sessions WHERE id=?', (session_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('personal') + '?tab=sessions')

@app.route('/admin/sessions/edit/<int:session_id>', methods=['POST'])
@admin_required
def admin_session_edit(session_id):
    film_id = request.form.get('film_id')
    hall_id = request.form.get('hall_id')
    date = request.form.get('date')
    time = request.form.get('time')
    price = request.form.get('price')

    conn = get_db()
    conn.execute('''
        UPDATE sessions SET film_id=?, hall_id=?, date=?, time=?, price=?
        WHERE id=?
    ''', (film_id, hall_id, date, time, price, session_id))
    conn.commit()
    conn.close()
    return redirect(url_for('personal') + '?tab=sessions')


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
    users = conn.execute('SELECT id, name, email, role, is_banned FROM users ORDER BY id').fetchall()
    conn.close()
    return render_template('admin/users.html', users=users, user=current_user())

@app.route('/admin/users/ban/<int:user_id>', methods=['POST'])
@admin_required
def admin_user_ban(user_id):
    user = current_user()
    if user['id'] == user_id:
        return redirect(url_for('personal') + '?tab=users')
    conn = get_db()
    current = conn.execute('SELECT is_banned FROM users WHERE id=?', (user_id,)).fetchone()
    new_status = 0 if current['is_banned'] else 1
    conn.execute('UPDATE users SET is_banned=? WHERE id=?', (new_status, user_id))
    conn.commit()
    conn.close()
    return redirect(url_for('personal') + '?tab=users')

@app.route('/admin/users/role/<int:user_id>', methods=['POST'])
@admin_required
def admin_user_role(user_id):
    user = current_user()
    if user['id'] == user_id:
        return redirect(url_for('personal') + '?tab=users')
    new_role = request.form.get('role')
    if new_role not in ('client', 'admin', 'cashier'):
        return redirect(url_for('personal') + '?tab=users')
    conn = get_db()
    conn.execute('UPDATE users SET role=? WHERE id=?', (new_role, user_id))
    conn.commit()
    conn.close()
    return redirect(url_for('personal') + '?tab=users')

@app.route('/terms')
def terms():
    return render_template('user/legal.html', type='terms', user=current_user())

@app.route('/privacy')
def privacy():
    return render_template('user/legal.html', type='privacy', user=current_user())


@app.route('/send_recovery_code', methods=['POST'])
def send_recovery_code():
    email = request.form.get('email', '').strip().lower()

    # Проверка пользователя в базе
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
    conn.close()

    if not user:
        return {"status": "error", "message": "Пользователь с такой почтой не найден"}, 404

    # Генерация кода
    code = str(random.randint(100000, 999999))
    session['recovery_code'] = code
    session['recovery_email'] = email
    session['recovery_time'] = time.time()

    # Отправка
    try:
        msg = Message("Код для восстановления пароля - Мир Кино",
                      recipients=[email])
        msg.html = f"""
            <div style="background-color: #0d0f14; padding: 40px; font-family: sans-serif; color: #e8eaf0; border-radius: 10px;">
                <div style="text-align: center; margin-bottom: 20px;">
                    <h2 style="color: #e8a020; margin: 0;">МИР КИНО</h2>
                </div>
                <div style="background-color: #161a23; padding: 30px; border-radius: 8px; border: 1px solid #2a2f3e;">
                    <p style="font-size: 16px;">Здравствуйте!</p>
                    <p style="font-size: 14px; color: #7a8399;">Вы запросили восстановление пароля. Используйте код ниже для подтверждения:</p>
                    <div style="font-size: 32px; font-weight: bold; color: #e8a020; text-align: center; letter-spacing: 10px; margin: 30px 0;">
                        {code}
                    </div>
                    <p style="font-size: 12px; color: #4a5066; text-align: center;">Если вы не запрашивали этот код, просто проигнорируйте письмо.</p>
                </div>
                <div style="text-align: center; margin-top: 20px; font-size: 12px; color: #4a5066;">
                    © 2026 Кинотеатр «Мир Кино»
                </div>
            </div>
        """

        mail.send(msg)

        return {"status": "success", "message": "Код успешно отправлен"}
    except Exception as e:
        print(f"Ошибка SMTP: {e}")
        return {"status": "error", "message": "Ошибка при отправке письма. Проверьте настройки почты."}, 500

# ─────────────────────────────────────────────
if __name__ == '__main__':
    init_db()
    app.run(debug=True)