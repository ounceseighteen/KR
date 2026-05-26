from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
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
app.config['MAIL_PASSWORD'] = 'ypso fgcr teng rhyt'
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
            booked_at TEXT,
            status TEXT NOT NULL DEFAULT 'booked',
            custom_code TEXT,
            promo_id INTEGER REFERENCES promotions(id),
            final_price REAL,
            payment_method TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (session_id) REFERENCES sessions(id),
            FOREIGN KEY (seat_id) REFERENCES seats(id)
        );
        
       CREATE TABLE IF NOT EXISTS promotions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            discount INTEGER DEFAULT 0,
            image TEXT
        );

        CREATE TABLE IF NOT EXISTS loyalty_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            card_number TEXT NOT NULL UNIQUE,
            bonus_balance INTEGER NOT NULL DEFAULT 0,
            total_spent REAL NOT NULL DEFAULT 0,
            level TEXT NOT NULL DEFAULT 'Basic',
            created_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS bonus_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            booking_id INTEGER,
            amount INTEGER NOT NULL,
            operation TEXT NOT NULL,
            balance_after INTEGER NOT NULL,
            created_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (booking_id) REFERENCES bookings(id)
        );
    ''')

    conn.commit()

    # Мягкая миграция для уже созданной БД: добавляем новые поля, если их нет
    booking_columns = [r['name'] for r in c.execute("PRAGMA table_info(bookings)").fetchall()]
    if 'payment_method' not in booking_columns:
        c.execute("ALTER TABLE bookings ADD COLUMN payment_method TEXT")

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


def get_loyalty_level(total_spent):
    total_spent = float(total_spent or 0)
    if total_spent >= 30000:
        return 'Platinum'
    if total_spent >= 15000:
        return 'Gold'
    if total_spent >= 5000:
        return 'Silver'
    return 'Basic'


def get_loyalty_cashback(level):
    return {
        'Basic': 3,
        'Silver': 5,
        'Gold': 10,
        'Platinum': 15
    }.get(level or 'Basic', 3)


def get_next_loyalty_level_info(total_spent):
    total_spent = float(total_spent or 0)
    if total_spent < 5000:
        return {'name': 'Silver', 'left': int(5000 - total_spent)}
    if total_spent < 15000:
        return {'name': 'Gold', 'left': int(15000 - total_spent)}
    if total_spent < 30000:
        return {'name': 'Platinum', 'left': int(30000 - total_spent)}
    return None


def generate_loyalty_card_number(conn):
    while True:
        card_number = 'MK-' + ''.join(str(random.randint(0, 9)) for _ in range(12))
        existing = conn.execute('SELECT id FROM loyalty_cards WHERE card_number=?', (card_number,)).fetchone()
        if not existing:
            return card_number


def create_loyalty_card(conn, user_id):
    existing = conn.execute('SELECT * FROM loyalty_cards WHERE user_id=?', (user_id,)).fetchone()
    if existing:
        return existing
    card_number = generate_loyalty_card_number(conn)
    conn.execute('''
        INSERT INTO loyalty_cards (user_id, card_number, bonus_balance, total_spent, level, created_at)
        VALUES (?, ?, 0, 0, 'Basic', ?)
    ''', (user_id, card_number, datetime.now().isoformat()))
    conn.commit()
    return conn.execute('SELECT * FROM loyalty_cards WHERE user_id=?', (user_id,)).fetchone()


def add_loyalty_history(conn, user_id, amount, operation, balance_after, booking_id=None):
    conn.execute('''
        INSERT INTO bonus_history (user_id, booking_id, amount, operation, balance_after, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, booking_id, int(amount), operation, int(balance_after), datetime.now().isoformat()))


def spend_bonuses_for_booking(conn, user_id, booking_id, amount):
    card = conn.execute('SELECT * FROM loyalty_cards WHERE user_id=?', (user_id,)).fetchone()
    if not card:
        return False, 'У пользователя нет бонусной карты'

    amount = int(round(float(amount or 0)))
    if amount <= 0:
        return True, None

    current_balance = int(card['bonus_balance'] or 0)
    if current_balance < amount:
        return False, 'Недостаточно бонусов на карте'

    new_balance = current_balance - amount
    conn.execute('UPDATE loyalty_cards SET bonus_balance=? WHERE user_id=?', (new_balance, user_id))
    add_loyalty_history(conn, user_id, -amount, 'Оплата билета бонусной картой', new_balance, booking_id)
    return True, None


def award_bonus_for_booking(conn, booking_id):
    booking = conn.execute('''
        SELECT b.id, b.user_id, b.status, b.final_price, b.payment_method, s.price as session_price
        FROM bookings b
        JOIN sessions s ON s.id = b.session_id
        WHERE b.id=?
    ''', (booking_id,)).fetchone()

    if not booking or booking['status'] != 'paid':
        return

    # Кешбэк начисляется только при оплате бонусной картой.
    # Обычная оплата банковской картой не влияет на бонусную карту.
    if booking['payment_method'] != 'bonus':
        return

    card = conn.execute('SELECT * FROM loyalty_cards WHERE user_id=?', (booking['user_id'],)).fetchone()
    if not card:
        return

    already = conn.execute('''
        SELECT id FROM bonus_history
        WHERE booking_id=? AND operation='Кешбэк за билет'
    ''', (booking_id,)).fetchone()
    if already:
        return

    final_price = float(booking['final_price'] or booking['session_price'] or 0)
    cashback = get_loyalty_cashback(card['level'])
    bonus_amount = int(final_price * cashback / 100)
    if bonus_amount <= 0:
        return

    new_total_spent = float(card['total_spent'] or 0) + final_price
    new_level = get_loyalty_level(new_total_spent)
    new_balance = int(card['bonus_balance'] or 0) + bonus_amount

    conn.execute('''
        UPDATE loyalty_cards
        SET bonus_balance=?, total_spent=?, level=?
        WHERE user_id=?
    ''', (new_balance, new_total_spent, new_level, booking['user_id']))

    add_loyalty_history(conn, booking['user_id'], bonus_amount, 'Кешбэк за билет', new_balance, booking_id)


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




def send_confirmation_email(email, subject, intro_text, code):
    msg = Message(subject, recipients=[email])
    msg.html = f"""
        <div style="background-color:#0d0f14; padding:40px; font-family:sans-serif; color:#e8eaf0; border-radius:10px;">
            <div style="text-align:center; margin-bottom:20px;">
                <h2 style="color:#e8a020; margin:0;">МИР КИНО</h2>
            </div>
            <div style="background-color:#161a23; padding:30px; border-radius:8px; border:1px solid #2a2f3e;">
                <p style="font-size:16px;">Здравствуйте!</p>
                <p style="font-size:14px; color:#7a8399;">{intro_text}</p>
                <div style="font-size:32px; font-weight:bold; color:#e8a020; text-align:center; letter-spacing:10px; margin:30px 0;">
                    {code}
                </div>
                <p style="font-size:12px; color:#4a5066; text-align:center;">Код действует 5 минут. Если вы не выполняли это действие, просто проигнорируйте письмо.</p>
            </div>
            <div style="text-align:center; margin-top:20px; font-size:12px; color:#4a5066;">
                © 2026 Кинотеатр «Мир Кино»
            </div>
        </div>
    """
    mail.send(msg)




def make_ticket_code(title, film_id, booking_id):
    """Код билета как в personal: первая буква фильма + id фильма + '-' + id бронирования."""
    first_letter = (title or 'Б')[0].upper()
    return f"{first_letter}{film_id}-{booking_id}"


def send_paid_tickets_email(recipient_email, booking_ids):
    """Отправляет одно письмо по одному или нескольким ОПЛАЧЕННЫМ билетам."""
    if not recipient_email or not booking_ids:
        return

    booking_ids = [int(x) for x in booking_ids if x]
    if not booking_ids:
        return

    conn = get_db()
    placeholders = ','.join('?' for _ in booking_ids)
    rows = conn.execute(f"""
        SELECT b.id, b.custom_code, b.final_price, b.payment_method,
               u.name as user_name, u.email as user_email,
               f.title, f.id as film_id, f.poster, s.date, s.time, h.name as hall_name,
               seats.row_num, seats.seat_num, p.title as promo_title, p.discount as promo_discount
        FROM bookings b
        JOIN users u ON u.id = b.user_id
        JOIN sessions s ON s.id = b.session_id
        JOIN films f ON f.id = s.film_id
        JOIN halls h ON h.id = s.hall_id
        JOIN seats ON seats.id = b.seat_id
        LEFT JOIN promotions p ON p.id = b.promo_id
        WHERE b.id IN ({placeholders}) AND b.status='paid'
        ORDER BY seats.row_num, seats.seat_num
    """, booking_ids).fetchall()
    conn.close()

    if not rows:
        return

    first = rows[0]
    poster_filename = first['poster'] or ''
    poster_path = os.path.join(app.root_path, 'static', 'posters', poster_filename) if poster_filename else ''
    has_poster = bool(poster_filename and os.path.exists(poster_path))

    try:
        date_text = datetime.strptime(first['date'], '%Y-%m-%d').strftime('%d.%m.%Y')
    except Exception:
        date_text = first['date']

    seats_text = ', '.join([f"ряд {r['row_num']}, место {r['seat_num']}" for r in rows])
    codes_text = '<br>'.join([make_ticket_code(r['title'], r['film_id'], r['id']) for r in rows])
    total_price = sum(float(r['final_price'] or 0) for r in rows)
    payment_text = 'Бонусная карта' if first['payment_method'] == 'bonus' else 'Банковская карта'

    promo_html = ''
    if first['promo_title']:
        promo_html = f"""
            <tr><td style="padding:7px 0; color:#7a8399;">Акция</td><td style="padding:7px 0; color:#e8eaf0; font-weight:700;">{first['promo_title']} −{first['promo_discount'] or 0}%</td></tr>
        """

    poster_html = """
        <div style="width:320px; height:500px; border-radius:12px; background:#1e2330; display:flex; align-items:center; justify-content:center; color:#e8a020; font-size:44px; font-weight:800;">🎬</div>
    """
    if has_poster:
        poster_html = '<img src="cid:ticket_poster" alt="Афиша" style="width:320px; height:500px; object-fit:cover; border-radius:12px; display:block;">'

    subject = f"Ваш билет в Мир Кино — {first['title']}"
    msg = Message(subject, recipients=[recipient_email])
    msg.html = f"""
        <div style="margin:0; padding:32px; background:#0d0f14; font-family:Arial, sans-serif; color:#e8eaf0;">
            <div style="max-width:720px; margin:0 auto;">
                <div style="text-align:center; margin-bottom:22px;">
                    <div style="font-size:24px; font-weight:900; color:#e8a020; letter-spacing:1px;">МИР КИНО</div>
                </div>

                <div style="background:#161a23; border:1px solid #2a2f3e; border-radius:16px; padding:22px;">
                    <div style="display:flex; gap:18px; align-items:flex-start;">
                        <div style="flex:0 0 320px;">{poster_html}</div>
                        <div style="flex:1; min-width:0; margin-left:22px;">
                            <h2 style="margin:0 0 14px; color:#e8eaf0; font-size:24px; line-height:1.25;">{first['title']}</h2>
                            <table style="width:100%; border-collapse:collapse; font-size:15px;">
                                <tr><td style="padding:7px 0; color:#7a8399; width:130px;">Дата</td><td style="padding:7px 0; color:#e8eaf0; font-weight:700;">{date_text}</td></tr>
                                <tr><td style="padding:7px 0; color:#7a8399;">Время</td><td style="padding:7px 0; color:#e8eaf0; font-weight:700;">{first['time']}</td></tr>
                                <tr><td style="padding:7px 0; color:#7a8399;">Зал</td><td style="padding:7px 0; color:#e8eaf0; font-weight:700;">{first['hall_name']}</td></tr>
                                <tr><td style="padding:7px 0; color:#7a8399;">Места</td><td style="padding:7px 0; color:#e8eaf0; font-weight:700;">{seats_text}</td></tr>
                                <tr><td style="padding:7px 0; color:#7a8399;">Оплата</td><td style="padding:7px 0; color:#e8eaf0; font-weight:700;">{payment_text}</td></tr>
                                {promo_html}
                                <tr><td style="padding:7px 0; color:#7a8399;">Сумма</td><td style="padding:7px 0; color:#e8a020; font-weight:900; font-size:18px;">{int(round(total_price))} ₽</td></tr>
                            </table>
                        </div>
                    </div>

                    <div style="margin-top:20px; padding:14px; background:#0d0f14; border:1px solid #2a2f3e; border-radius:12px; color:#e8eaf0; font-size:14px; line-height:1.7;">
                        <div style="color:#7a8399; margin-bottom:6px;">Коды билетов:</div>
                        {codes_text}
                    </div>
                </div>

                <div style="text-align:center; margin-top:18px; color:#4a5066; font-size:12px;">
                    Покажите письмо или код билета при посещении кинотеатра.<br>
                    © 2026 Кинотеатр «Мир Кино»
                </div>
            </div>
        </div>
    """

    if has_poster:
        with open(poster_path, 'rb') as img:
            ext = os.path.splitext(poster_filename)[1].lower().lstrip('.') or 'jpg'
            mimetype = 'image/png' if ext == 'png' else 'image/jpeg'
            msg.attach(
                filename=poster_filename,
                content_type=mimetype,
                data=img.read(),
                disposition='inline',
                headers={'Content-ID': '<ticket_poster>'}
            )

    try:
        mail.send(msg)
    except Exception as e:
        print('Ошибка отправки письма с билетами:', e)
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
    today = date.today().isoformat()
    now_time = datetime.now().strftime('%H:%M')

    # Все фильмы
    films = conn.execute('SELECT * FROM films').fetchall()

    # Топ 5 по купленным билетам
    top_films = conn.execute('''
        SELECT f.*, COUNT(b.id) as ticket_count
        FROM films f
        LEFT JOIN sessions s ON s.film_id = f.id
        LEFT JOIN bookings b ON b.session_id = s.id AND b.status = 'paid'
        GROUP BY f.id
        ORDER BY ticket_count DESC
        LIMIT 5
    ''').fetchall()

    # Сегодня в кино (только предстоящие)
    upcoming = conn.execute('''
        SELECT DISTINCT f.*, MIN(s.time) as next_time
        FROM sessions s
        JOIN films f ON s.film_id = f.id
        JOIN halls h ON s.hall_id = h.id
        WHERE s.date = ? AND s.time > ?
        GROUP BY f.id
        ORDER BY next_time
    ''', (today, now_time)).fetchall()

    promotions = conn.execute('SELECT * FROM promotions ORDER BY id').fetchall()

    conn.close()
    return render_template('user/index.html',
                           films=films,
                           top_films=top_films,
                           upcoming=upcoming,
                           promotions=promotions,
                           user=user,
                           today_str=today)

@app.route('/films')
def all_films():
    conn = get_db()
    today = date.today().isoformat()
    now_time = datetime.now().strftime('%H:%M')

    films = conn.execute('''
        SELECT f.*,
               COUNT(DISTINCT b.id) as ticket_count,
               MIN(CASE WHEN s.date > ? OR (s.date = ? AND s.time > ?)
                        THEN s.date || ' ' || s.time ELSE NULL END) as next_session
        FROM films f
        LEFT JOIN sessions s ON s.film_id = f.id
        LEFT JOIN bookings b ON b.session_id = s.id AND b.status = 'paid'
        GROUP BY f.id
        ORDER BY f.title
    ''', (today, today, now_time)).fetchall()

    genres = conn.execute('SELECT DISTINCT genre FROM films WHERE genre IS NOT NULL ORDER BY genre').fetchall()
    promotions = conn.execute('SELECT * FROM promotions ORDER BY id').fetchall()
    conn.close()
    return render_template('user/films.html', films=films, genres=genres, promotions=promotions, user=current_user())

@app.route('/promotions')
def promotions():
    conn = get_db()
    promos = conn.execute('SELECT * FROM promotions ORDER BY id').fetchall()
    conn.close()
    return render_template('user/promotions.html', promos=promos, user=current_user())

@app.route('/loyalty')
def loyalty():
    user = current_user()
    levels = [
        {'name': 'Basic', 'limit': 'сразу после выпуска', 'cashback': 3},
        {'name': 'Silver', 'limit': 'от 5 000 ₽ покупок', 'cashback': 5},
        {'name': 'Gold', 'limit': 'от 15 000 ₽ покупок', 'cashback': 10},
        {'name': 'Platinum', 'limit': 'от 30 000 ₽ покупок', 'cashback': 15},
    ]

    card = None
    history = []
    next_level = None
    stats = {'paid_tickets': 0, 'paid_sum': 0}

    if user and user['role'] == 'client':
        conn = get_db()
        card = conn.execute('SELECT * FROM loyalty_cards WHERE user_id=?', (user['id'],)).fetchone()
        if card:
            history = conn.execute('''
                SELECT h.*,
                       f.title as film_title,
                       s.date as session_date,
                       s.time as session_time,
                       halls.name as hall_name,
                       seats.row_num,
                       seats.seat_num,
                       COALESCE(b.final_price, s.price) as ticket_price,
                       b.payment_method
                FROM bonus_history h
                LEFT JOIN bookings b ON b.id = h.booking_id
                LEFT JOIN sessions s ON s.id = b.session_id
                LEFT JOIN films f ON f.id = s.film_id
                LEFT JOIN halls ON halls.id = s.hall_id
                LEFT JOIN seats ON seats.id = b.seat_id
                WHERE h.user_id=?
                ORDER BY h.id DESC
                LIMIT 20
            ''', (user['id'],)).fetchall()
            next_level = get_next_loyalty_level_info(card['total_spent'])
        stats_row = conn.execute('''
            SELECT COUNT(*) as paid_tickets,
                   COALESCE(SUM(COALESCE(b.final_price, s.price)), 0) as paid_sum
            FROM bookings b
            JOIN sessions s ON s.id = b.session_id
            WHERE b.user_id=? AND b.status='paid' AND b.payment_method='bonus'
        ''', (user['id'],)).fetchone()
        stats = dict(stats_row)
        conn.close()

    return render_template('user/loyalty.html',
                           user=user,
                           card=card,
                           history=history,
                           levels=levels,
                           next_level=next_level,
                           stats=stats)


@app.route('/loyalty/create', methods=['POST'])
@login_required
def loyalty_create():
    # Прямой выпуск карты отключён: карта создаётся только после подтверждения кода из письма.
    flash('Для выпуска бонусной карты подтвердите код из письма.', 'warning')
    return redirect(url_for('loyalty'))


@app.route('/loyalty/topup', methods=['POST'])
@login_required
def loyalty_topup():
    user = current_user()
    if not user or user['role'] != 'client':
        return redirect(url_for('index'))

    amount = request.form.get('amount', type=int)
    if not amount or amount <= 0:
        flash('Введите корректную сумму пополнения', 'danger')
        return redirect(url_for('loyalty'))

    conn = get_db()
    card = create_loyalty_card(conn, user['id'])
    new_balance = int(card['bonus_balance'] or 0) + amount
    conn.execute('UPDATE loyalty_cards SET bonus_balance=? WHERE user_id=?', (new_balance, user['id']))
    add_loyalty_history(conn, user['id'], amount, 'Пополнение карты', new_balance)
    conn.commit()
    conn.close()

    flash('Баланс бонусной карты пополнен', 'success')
    return redirect(url_for('loyalty'))

@app.route('/film/<int:film_id>')
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
    now_dt = datetime.now()

    loyalty_card = conn.execute("""
        SELECT * FROM loyalty_cards WHERE user_id=?
    """, (user['id'],)).fetchone()

    raw_bookings = conn.execute("""
        SELECT b.*, f.title, s.date, s.time, h.name as hall_name,
               se.row_num, se.seat_num, s.price as session_price,
               COALESCE(b.final_price, s.price) as display_price,
               p.title as promo_title,
               p.discount as promo_discount
        FROM bookings b
        JOIN sessions s ON b.session_id = s.id
        JOIN films f ON s.film_id = f.id
        JOIN halls h ON s.hall_id = h.id
        JOIN seats se ON b.seat_id = se.id
        LEFT JOIN promotions p ON p.id = b.promo_id
        WHERE b.user_id=? AND b.status != 'cancelled'
        ORDER BY s.date DESC, s.time DESC, b.id DESC
    """, (user['id'],)).fetchall()

    bookings = []
    for b in raw_bookings:
        item = dict(b)
        try:
            session_dt = datetime.strptime(f"{item['date']} {item['time']}", "%Y-%m-%d %H:%M")
        except Exception:
            session_dt = now_dt

        item['is_past'] = session_dt < now_dt
        item['date_text'] = datetime.strptime(item['date'], "%Y-%m-%d").strftime("%d.%m.%Y") if item.get('date') else ''
        item['price'] = item.get('display_price') or item.get('session_price') or 0

        if item['status'] == 'paid' and item['is_past']:
            item['status_label'] = 'Посещён'
            item['status_color'] = 'var(--text-muted)'
            item['can_cancel'] = False
            item['can_pay'] = False
        elif item['status'] == 'paid':
            item['status_label'] = 'Куплен'
            item['status_color'] = 'var(--success)'
            item['can_cancel'] = False
            item['can_pay'] = False
        elif item['status'] == 'booked' and item['is_past']:
            item['status_label'] = 'Просрочен'
            item['status_color'] = 'var(--danger)'
            item['can_cancel'] = False
            item['can_pay'] = False
        else:
            item['status_label'] = 'Забронирован'
            item['status_color'] = 'var(--accent)'
            item['can_cancel'] = True
            item['can_pay'] = True

        if item.get('payment_method') == 'bonus':
            item['payment_text'] = 'Бонусная карта'
        elif item.get('payment_method') == 'bank':
            item['payment_text'] = 'Банковская карта'
        else:
            item['payment_text'] = 'Не оплачен'

        bookings.append(item)

    stats_row = conn.execute("""
        SELECT COUNT(*) as bought_tickets,
               COALESCE(SUM(COALESCE(b.final_price, s.price)), 0) as total_spent
        FROM bookings b
        JOIN sessions s ON s.id = b.session_id
        WHERE b.user_id=? AND b.status='paid'
    """, (user['id'],)).fetchone()

    visited_row = conn.execute("""
        SELECT COUNT(*) as visited_films
        FROM bookings b
        JOIN sessions s ON s.id = b.session_id
        WHERE b.user_id=?
          AND b.status='paid'
          AND (s.date < ? OR (s.date = ? AND s.time < ?))
    """, (user['id'], date.today().isoformat(), date.today().isoformat(), datetime.now().strftime('%H:%M'))).fetchone()

    cabinet_stats = {
        'bought_tickets': stats_row['bought_tickets'] if stats_row else 0,
        'visited_films': visited_row['visited_films'] if visited_row else 0,
        'total_spent': stats_row['total_spent'] if stats_row else 0
    }

    promotions = conn.execute('SELECT * FROM promotions ORDER BY id').fetchall()

    conn.close()
    return render_template('user/cabinet.html',
                           user=user,
                           bookings=bookings,
                           loyalty_card=loyalty_card,
                           cabinet_stats=cabinet_stats,
                           promotions=promotions)


@app.route('/personal')
def personal():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()

    if not user or user['role'] == 'client':
        conn.close()
        return redirect(url_for('index'))

    data = {}
    data['today'] = date.today().isoformat()
    data['now_time'] = datetime.now().strftime('%H:%M')

    if user['role'] in ('admin', 'cashier'):
        data['films'] = conn.execute('SELECT * FROM films ORDER BY id').fetchall()
        data['halls'] = conn.execute('SELECT * FROM halls ORDER BY id').fetchall()
        data['promotions'] = conn.execute('SELECT * FROM promotions ORDER BY id').fetchall()

    if user['role'] == 'admin':
        data['users'] = conn.execute('''
            SELECT u.id, u.name, u.email, u.role, u.is_banned,
                   lc.card_number as loyalty_card_number,
                   lc.level as loyalty_level,
                   lc.bonus_balance as loyalty_bonus_balance,
                   lc.total_spent as loyalty_total_spent
            FROM users u
            LEFT JOIN loyalty_cards lc ON lc.user_id = u.id
            ORDER BY u.id
        ''').fetchall()
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

    # 1. Автоматическая отмена просроченных броней (за 30 минут до сеанса)
    deadline_time = (datetime.now() + timedelta(minutes=30)).strftime('%H:%M')
    current_date = date.today().strftime('%Y-%m-%d')

    conn.execute('''
        UPDATE bookings 
        SET status = 'cancelled' 
        WHERE status = 'booked' 
          AND session_id IN (
              SELECT id FROM sessions 
              WHERE date < ? OR (date = ? AND time <= ?)
          )
    ''', (current_date, current_date, deadline_time))
    conn.commit()

    # 2. Получаем данные из БД с правильным JOIN таблицы seats
    if user['role'] == 'admin':
        raw_bookings = conn.execute('''
            SELECT b.id, b.user_id, b.session_id, b.status,
                   b.promo_id, b.final_price,
                   st.row_num, st.seat_num,
                   u.email as user_email, u.name as user_name,
                   s.date, s.time, s.price as session_price,
                   f.title, f.id as film_id,
                   p.title as promo_title, p.discount as promo_discount
            FROM bookings b
            JOIN users u ON b.user_id = u.id
            JOIN sessions s ON b.session_id = s.id
            JOIN films f ON s.film_id = f.id
            JOIN seats st ON b.seat_id = st.id
            LEFT JOIN promotions p ON b.promo_id = p.id
            ORDER BY b.id DESC
        ''').fetchall()
    elif user['role'] == 'cashier':
        raw_bookings = conn.execute('''
            SELECT b.id, b.user_id, b.session_id, b.status,
                   b.promo_id, b.final_price,
                   st.row_num, st.seat_num,
                   u.email as user_email, u.name as user_name,
                   s.date, s.time, s.price as session_price,
                   f.title, f.id as film_id,
                   p.title as promo_title, p.discount as promo_discount
            FROM bookings b
            JOIN users u ON b.user_id = u.id
            JOIN sessions s ON b.session_id = s.id
            JOIN films f ON s.film_id = f.id
            JOIN seats st ON b.seat_id = st.id
            LEFT JOIN promotions p ON b.promo_id = p.id
            WHERE b.status = 'booked'
            ORDER BY s.date ASC, s.time ASC
        ''').fetchall()
    else:
        raw_bookings = []

    # 3. Обработка данных на лету и генерация уникального кода
    bookings_list = []
    for b in raw_bookings:
        b_dict = dict(b)

        # Первая буква названия фильма
        first_letter = b_dict['title'][0].upper() if b_dict['title'] else 'Б'
        film_id = b_dict['film_id']
        booking_id = b_dict['id']

        # Собираем короткий кастомный код билета (например: Х3-12)
        b_dict['custom_code'] = f"{first_letter}{film_id}-{booking_id}"

        # Склеиваем ряд и место из привязанной таблицы seats
        b_dict['seats_text'] = f"Ряд {b_dict['row_num']}, место {b_dict['seat_num']}"

        # Защита для шаблона: у старых/неполных выборок поля акции и цены могут отсутствовать.
        if 'session_price' not in b_dict:
            b_dict['session_price'] = b_dict.get('price', 0) or 0
        if 'promo_title' not in b_dict:
            b_dict['promo_title'] = None
        if 'promo_discount' not in b_dict:
            b_dict['promo_discount'] = 0
        if 'final_price' not in b_dict or b_dict.get('final_price') is None:
            b_dict['final_price'] = b_dict.get('session_price', 0) or 0

        bookings_list.append(b_dict)

    data['bookings'] = bookings_list

    conn.close()
    return render_template('admin/personal.html', user=user, **data)

@app.route('/confirm_payment/<int:booking_id>', methods=['POST'])
def confirm_payment(booking_id):
    if 'user_id' not in session:
        return redirect(url_for('index'))

    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()

    if not user or user['role'] not in ('admin', 'cashier'):
        conn.close()
        flash('У вас нет прав для подтверждения оплаты.', 'danger')
        return redirect(url_for('personal'))

    recipient = conn.execute('''
        SELECT u.email, b.custom_code, f.title as film_title, f.id as film_id
        FROM bookings b
        JOIN users u ON u.id = b.user_id
        JOIN sessions s ON s.id = b.session_id
        JOIN films f ON f.id = s.film_id
        WHERE b.id=?
    ''', (booking_id,)).fetchone()

    # Обновляем статус билета на "оплачен"
    conn.execute("UPDATE bookings SET status = 'paid', payment_method = COALESCE(payment_method, 'bank') WHERE id = ?", (booking_id,))
    if recipient and not recipient['custom_code']:
        conn.execute('UPDATE bookings SET custom_code=? WHERE id=?',
                     (make_ticket_code(recipient['film_title'], recipient['film_id'], booking_id), booking_id))
    award_bonus_for_booking(conn, booking_id)
    conn.commit()
    conn.close()

    if recipient:
        send_paid_tickets_email(recipient['email'], [booking_id])

    return redirect(url_for('personal') + '?tab=bookings')

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


@app.route('/send_registration_code', methods=['POST'])
def send_registration_code():
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    confirm_password = request.form.get('confirm_password', '')

    if not name:
        return {"status": "error", "message": "Введите имя"}, 400
    if not is_valid_email(email):
        return {"status": "error", "message": "Некорректный формат почты"}, 400
    if len(password) < 6:
        return {"status": "error", "message": "Минимум 6 символов"}, 400
    if password != confirm_password:
        return {"status": "error", "message": "Пароли не совпадают"}, 400

    conn = get_db()
    existing = conn.execute('SELECT id FROM users WHERE email=?', (email,)).fetchone()
    conn.close()
    if existing:
        return {"status": "error", "message": "Email уже зарегистрирован"}, 400

    code = str(random.randint(100000, 999999))
    session['registration_code'] = code
    session['registration_time'] = time.time()
    session['pending_registration'] = {
        'name': name,
        'email': email,
        'password_hash': hash_password(password)
    }

    try:
        send_confirmation_email(
            email,
            "Код подтверждения регистрации - Мир Кино",
            "Для завершения регистрации введите код подтверждения:",
            code
        )
        return {"status": "success", "message": "Код отправлен"}
    except Exception as e:
        print(f"Ошибка SMTP при регистрации: {e}")
        return {"status": "error", "message": "Ошибка при отправке письма. Проверьте настройки почты."}, 500


@app.route('/resend_registration_code', methods=['POST'])
def resend_registration_code():
    pending = session.get('pending_registration')
    if not pending or not pending.get('email'):
        return {"status": "error", "message": "Данные регистрации не найдены. Заполните форму ещё раз."}, 400

    email = pending['email']
    conn = get_db()
    existing = conn.execute('SELECT id FROM users WHERE email=?', (email,)).fetchone()
    conn.close()
    if existing:
        return {"status": "error", "message": "Email уже зарегистрирован"}, 400

    code = str(random.randint(100000, 999999))
    session['registration_code'] = code
    session['registration_time'] = time.time()

    try:
        send_confirmation_email(
            email,
            "Код подтверждения регистрации - Мир Кино",
            "Для завершения регистрации введите код подтверждения:",
            code
        )
        return {"status": "success", "message": "Код отправлен"}
    except Exception as e:
        print(f"Ошибка SMTP при повторной отправке кода регистрации: {e}")
        return {"status": "error", "message": "Ошибка при отправке письма. Проверьте настройки почты."}, 500


@app.route('/verify_registration_code', methods=['POST'])
def verify_registration_code():
    input_code = request.form.get('code', '').strip()
    stored_code = session.get('registration_code')
    stored_time = session.get('registration_time')
    pending = session.get('pending_registration')

    if not stored_code or not stored_time or not pending:
        return {"status": "error", "message": "Код не найден. Запросите новый."}, 400
    if time.time() - stored_time > 300:
        session.pop('registration_code', None)
        session.pop('registration_time', None)
        session.pop('pending_registration', None)
        return {"status": "error", "message": "Код истёк. Зарегистрируйтесь ещё раз."}, 400
    if input_code != stored_code:
        return {"status": "error", "message": "Неверный код"}, 400

    conn = get_db()
    existing = conn.execute('SELECT id FROM users WHERE email=?', (pending['email'],)).fetchone()
    if existing:
        conn.close()
        return {"status": "error", "message": "Email уже зарегистрирован"}, 400

    conn.execute('INSERT INTO users (name, email, password, role) VALUES (?,?,?,?)',
                 (pending['name'], pending['email'], pending['password_hash'], 'client'))
    conn.commit()
    user = conn.execute('SELECT * FROM users WHERE email=?', (pending['email'],)).fetchone()
    conn.close()

    session['user_id'] = user['id']
    session.pop('registration_code', None)
    session.pop('registration_time', None)
    session.pop('pending_registration', None)
    return {"status": "success", "message": "Регистрация завершена", "redirect": url_for('index')}


@app.route('/send_loyalty_code', methods=['POST'])
@login_required
def send_loyalty_code():
    user = current_user()
    if not user or user['role'] != 'client':
        return {"status": "error", "message": "Карта доступна только клиентам"}, 403

    conn = get_db()
    existing = conn.execute('SELECT id FROM loyalty_cards WHERE user_id=?', (user['id'],)).fetchone()
    conn.close()
    if existing:
        return {"status": "error", "message": "Карта уже выпущена"}, 400

    code = str(random.randint(100000, 999999))
    session['loyalty_code'] = code
    session['loyalty_time'] = time.time()

    try:
        send_confirmation_email(
            user['email'],
            "Код для выпуска бонусной карты - Мир Кино",
            "Для выпуска бонусной карты введите код подтверждения:",
            code
        )
        return {"status": "success", "message": "Код отправлен"}
    except Exception as e:
        print(f"Ошибка SMTP при выпуске карты: {e}")
        return {"status": "error", "message": "Ошибка при отправке письма. Проверьте настройки почты."}, 500


@app.route('/verify_loyalty_code', methods=['POST'])
@login_required
def verify_loyalty_code():
    user = current_user()
    if not user or user['role'] != 'client':
        return {"status": "error", "message": "Карта доступна только клиентам"}, 403

    input_code = request.form.get('code', '').strip()
    stored_code = session.get('loyalty_code')
    stored_time = session.get('loyalty_time')

    if not stored_code or not stored_time:
        return {"status": "error", "message": "Код не найден. Запросите новый."}, 400
    if time.time() - stored_time > 300:
        session.pop('loyalty_code', None)
        session.pop('loyalty_time', None)
        return {"status": "error", "message": "Код истёк. Запросите новый."}, 400
    if input_code != stored_code:
        return {"status": "error", "message": "Неверный код"}, 400

    conn = get_db()
    create_loyalty_card(conn, user['id'])
    conn.close()
    session.pop('loyalty_code', None)
    session.pop('loyalty_time', None)
    return {"status": "success", "message": "Бонусная карта выпущена", "redirect": url_for('loyalty')}


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
        conn.close()
        flash('Подтвердите регистрацию кодом из письма.', 'warning')
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

# --- Акции ---
@app.route('/admin/promotions/add', methods=['POST'])
@admin_required
def admin_promotion_add():
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    discount = request.form.get('discount', 0)
    if not title:
        return redirect(url_for('personal') + '?tab=promotions')

    conn = get_db()
    conn.execute('INSERT INTO promotions (title, description, discount) VALUES (?,?,?)',
                 (title, description, discount))
    promo_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]

    image_file = request.files.get('image')
    if image_file and image_file.filename:
        ext = os.path.splitext(image_file.filename)[1].lower()
        filename = f"promo_{uuid.uuid4().hex}{ext}"
        save_path = os.path.join('static', 'promotions', filename)
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        image_file.save(save_path)
        conn.execute('UPDATE promotions SET image=? WHERE id=?', (filename, promo_id))

    conn.commit()
    conn.close()
    return redirect(url_for('personal') + '?tab=promotions')

@app.route('/admin/promotions/delete/<int:promo_id>', methods=['POST'])
@admin_required
def admin_promotion_delete(promo_id):
    conn = get_db()
    promo = conn.execute('SELECT image FROM promotions WHERE id=?', (promo_id,)).fetchone()
    if promo and promo['image']:
        path = os.path.join('static', 'promotions', promo['image'])
        if os.path.exists(path):
            os.remove(path)
    conn.execute('DELETE FROM promotions WHERE id=?', (promo_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('personal') + '?tab=promotions')

@app.route('/admin/promotions/image/<int:promo_id>', methods=['POST'])
@admin_required
def admin_promotion_image(promo_id):
    image_file = request.files.get('image')
    if image_file and image_file.filename:
        ext = os.path.splitext(image_file.filename)[1].lower()
        filename = f"promo_{uuid.uuid4().hex}{ext}"
        save_path = os.path.join('static', 'promotions', filename)
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        image_file.save(save_path)
        conn = get_db()
        conn.execute('UPDATE promotions SET image=? WHERE id=?', (filename, promo_id))
        conn.commit()
        conn.close()
    return redirect(url_for('personal') + '?tab=promotions')

@app.route('/admin/promotions/desc/<int:promo_id>', methods=['POST'])
@admin_required
def admin_promotion_desc(promo_id):
    description = request.form.get('description', '').strip()
    conn = get_db()
    conn.execute('UPDATE promotions SET description=? WHERE id=?', (description, promo_id))
    conn.commit()
    conn.close()
    return redirect(url_for('personal') + '?tab=promotions')

@app.route('/admin/promotions/edit/<int:promo_id>', methods=['POST'])
@admin_required
def admin_promotion_edit(promo_id):
    title = request.form.get('title', '').strip()
    discount = request.form.get('discount', 0)
    if not title:
        return redirect(url_for('personal') + '?tab=promotions')
    conn = get_db()
    conn.execute('UPDATE promotions SET title=?, discount=? WHERE id=?', (title, discount, promo_id))
    conn.commit()
    conn.close()
    return redirect(url_for('personal') + '?tab=promotions')

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

@app.route('/admin/films/desc/<int:film_id>', methods=['POST'])
@admin_required
def admin_film_desc(film_id):
    description = request.form.get('description', '').strip()
    conn = get_db()
    conn.execute('UPDATE films SET description=? WHERE id=?', (description, film_id))
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


# --- Продажа ---
@app.route('/api/session_seats/<int:session_id>')
def api_session_seats(session_id):
    conn = get_db()
    sess = conn.execute('''
        SELECT s.*, f.title, f.poster, h.name as hall_name, h.rows, h.seats_per_row, h.capacity
        FROM sessions s
        JOIN films f ON s.film_id = f.id
        JOIN halls h ON s.hall_id = h.id
        WHERE s.id=?
    ''', (session_id,)).fetchone()

    booked_seat_ids = [r['seat_id'] for r in
        conn.execute("SELECT seat_id FROM bookings WHERE session_id=? AND status != 'cancelled'",
                     (session_id,)).fetchall()]

    seats = conn.execute('SELECT * FROM seats WHERE hall_id=? ORDER BY row_num, seat_num',
                         (sess['hall_id'],)).fetchall()
    conn.close()

    rows = {}
    for seat in seats:
        r = seat['row_num']
        if r not in rows:
            rows[r] = []
        rows[r].append({
            'id': seat['id'],
            'num': seat['seat_num'],
            'booked': seat['id'] in booked_seat_ids
        })

    return {
        'title': sess['title'],
        'poster': sess['poster'],
        'hall_name': sess['hall_name'],
        'date': sess['date'],
        'time': sess['time'],
        'price': sess['price'],
        'rows': {str(k): v for k, v in rows.items()}
    }

@app.route('/admin/sell_ticket', methods=['POST'])
@login_required
def sell_ticket():
    session_id = request.form.get('session_id', type=int)
    client_email = request.form.get('client_email', '').strip()
    seat_ids = request.form.getlist('seat_ids')
    promo_id = request.form.get('promo_id', type=int)
    payment_method = request.form.get('payment_method', '').strip()

    if payment_method not in ('bank', 'bonus'):
        return jsonify({'error': 'Выберите способ оплаты'}), 400

    conn = get_db()
    client = conn.execute('SELECT id FROM users WHERE email=?', (client_email,)).fetchone()
    if not client:
        conn.close()
        return jsonify({'error': 'Клиент не найден'}), 404

    sess = conn.execute('''
        SELECT s.price, f.id as film_id, f.title as film_title
        FROM sessions s
        JOIN films f ON f.id = s.film_id
        WHERE s.id=?
    ''', (session_id,)).fetchone()
    base_price = sess['price']

    discount = 0
    if promo_id:
        promo = conn.execute('SELECT discount FROM promotions WHERE id=?', (promo_id,)).fetchone()
        if promo:
            discount = promo['discount']

    final_price = round(base_price * (1 - discount / 100), 2)

    if payment_method == 'bonus':
        card = conn.execute('SELECT * FROM loyalty_cards WHERE user_id=?', (client['id'],)).fetchone()
        total_to_spend = int(round(final_price)) * len(seat_ids)
        if not card:
            conn.close()
            return jsonify({'error': 'У клиента нет бонусной карты'}), 400
        if int(card['bonus_balance'] or 0) < total_to_spend:
            conn.close()
            return jsonify({'error': 'Недостаточно бонусов на карте клиента'}), 400

    paid_booking_ids = []

    for seat_id in seat_ids:
        existing = conn.execute(
            "SELECT id FROM bookings WHERE session_id=? AND seat_id=? AND status != 'cancelled'",
            (session_id, int(seat_id))).fetchone()
        if existing:
            conn.close()
            return jsonify({'error': 'Место уже занято'}), 400
        cur = conn.execute('''INSERT INTO bookings
            (user_id, session_id, seat_id, booked_at, status, custom_code, promo_id, final_price, payment_method)
            VALUES (?,?,?,?,?,?,?,?,?)''',
            (client['id'], session_id, int(seat_id),
             datetime.now().isoformat(), 'paid', None, promo_id, final_price, payment_method))

        booking_id = cur.lastrowid
        custom_code = make_ticket_code(sess['film_title'], sess['film_id'], booking_id)
        conn.execute('UPDATE bookings SET custom_code=? WHERE id=?', (custom_code, booking_id))

        paid_booking_ids.append(booking_id)

        if payment_method == 'bonus':
            ok, err = spend_bonuses_for_booking(conn, client['id'], booking_id, final_price)
            if not ok:
                conn.close()
                return jsonify({'error': err}), 400
            award_bonus_for_booking(conn, booking_id)

    conn.commit()
    conn.close()
    send_paid_tickets_email(client_email, paid_booking_ids)
    return jsonify({
        'ok': True,
        'message': 'Билеты оплачены и отправлены на указанную почту'
    })

@app.route('/api/film_sessions/<int:film_id>')
@login_required
def api_film_sessions(film_id):
    from datetime import date, datetime
    today = date.today().isoformat()
    now_time = datetime.now().strftime('%H:%M')
    conn = get_db()
    sessions = conn.execute('''
        SELECT s.id, s.date, s.time, s.price, h.name as hall_name
        FROM sessions s
        JOIN halls h ON h.id = s.hall_id
        WHERE s.film_id = ?
        AND (s.date > ? OR (s.date = ? AND s.time > ?))
        ORDER BY s.date, s.time
    ''', (film_id, today, today, now_time)).fetchall()
    conn.close()
    return {'sessions': [dict(s) for s in sessions]}

@app.route('/api/film/<int:film_id>')
def api_film(film_id):
    from datetime import date, datetime, timedelta
    today = date.today()
    week_later = today + timedelta(days=7)
    now_time = datetime.now().strftime('%H:%M')
    today_iso = today.isoformat()

    conn = get_db()
    film = conn.execute('SELECT * FROM films WHERE id=?', (film_id,)).fetchone()
    if not film:
        conn.close()
        return {'error': 'not found'}, 404

    sessions = conn.execute('''
        SELECT s.id, s.date, s.time, s.price, h.name as hall_name, h.format
        FROM sessions s
        JOIN halls h ON h.id = s.hall_id
        WHERE s.film_id = ?
        AND (s.date > ? OR (s.date = ? AND s.time > ?))
        AND s.date <= ?
        ORDER BY s.date, s.time
    ''', (film_id, today_iso, today_iso, now_time, week_later.isoformat())).fetchall()
    conn.close()

    # Группируем по датам
    days_ru = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
    months_ru = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']
    dates = {}
    for s in sessions:
        d = s['date']
        if d not in dates:
            dt = date.fromisoformat(d)
            dates[d] = {
                'label': f"{dt.day} {months_ru[dt.month-1]}",
                'weekday': days_ru[dt.weekday()],
                'sessions': []
            }
        dates[d]['sessions'].append({
            'id': s['id'],
            'time': s['time'],
            'date': s['date'],
            'price': s['price'],
            'hall_name': s['hall_name'],
            'format': s['format']
        })

    return {
        'id': film['id'],
        'title': film['title'],
        'description': film['description'] or '',
        'genre': film['genre'] or '',
        'duration': film['duration'] or 0,
        'poster': film['poster'] or '',
        'dates': dates
    }

@app.route('/client/book', methods=['POST'])
@login_required
def client_book():
    session_id = request.form.get('session_id', type=int)
    seat_ids = request.form.getlist('seat_ids')
    action = request.form.get('action', 'book')
    promo_id = request.form.get('promo_id', type=int)
    payment_method = request.form.get('payment_method', '').strip()
    user = current_user()

    if action == 'pay' and payment_method not in ('bank', 'bonus'):
        return jsonify({'error': 'Выберите способ оплаты'}), 400

    conn = get_db()
    sess = conn.execute('''
        SELECT s.price, f.id as film_id, f.title as film_title
        FROM sessions s
        JOIN films f ON f.id = s.film_id
        WHERE s.id=?
    ''', (session_id,)).fetchone()
    base_price = sess['price']

    discount = 0
    if promo_id:
        promo = conn.execute('SELECT discount FROM promotions WHERE id=?', (promo_id,)).fetchone()
        if promo:
            discount = promo['discount']

    final_price = round(base_price * (1 - discount / 100), 2)
    status = 'paid' if action == 'pay' else 'booked'

    if status == 'paid' and payment_method == 'bonus':
        card = conn.execute('SELECT * FROM loyalty_cards WHERE user_id=?', (user['id'],)).fetchone()
        total_to_spend = int(round(final_price)) * len(seat_ids)
        if not card:
            conn.close()
            return jsonify({'error': 'У вас нет бонусной карты'}), 400
        if int(card['bonus_balance'] or 0) < total_to_spend:
            conn.close()
            return jsonify({'error': 'Недостаточно бонусов на карте'}), 400

    paid_booking_ids = []

    for seat_id in seat_ids:
        existing = conn.execute(
            "SELECT id FROM bookings WHERE session_id=? AND seat_id=? AND status != 'cancelled'",
            (session_id, int(seat_id))).fetchone()
        if existing:
            conn.close()
            return jsonify({'error': 'Место уже занято'}), 400
        cur = conn.execute('''INSERT INTO bookings
            (user_id, session_id, seat_id, booked_at, status, custom_code, promo_id, final_price, payment_method)
            VALUES (?,?,?,?,?,?,?,?,?)''',
            (user['id'], session_id, int(seat_id),
             datetime.now().isoformat(), status, None, promo_id, final_price,
             payment_method if status == 'paid' else None))

        booking_id = cur.lastrowid
        custom_code = make_ticket_code(sess['film_title'], sess['film_id'], booking_id)
        conn.execute('UPDATE bookings SET custom_code=? WHERE id=?', (custom_code, booking_id))

        if status == 'paid':
            paid_booking_ids.append(booking_id)

        if status == 'paid' and payment_method == 'bonus':
            ok, err = spend_bonuses_for_booking(conn, user['id'], booking_id, final_price)
            if not ok:
                conn.close()
                return jsonify({'error': err}), 400
            award_bonus_for_booking(conn, booking_id)

    conn.commit()
    conn.close()
    if paid_booking_ids:
        send_paid_tickets_email(user['email'], paid_booking_ids)
    return jsonify({
        'ok': True,
        'message': 'Билеты оплачены и отправлены на вашу почту' if paid_booking_ids else 'Места забронированы'
    })


@app.route('/client/pay_booking/<int:booking_id>', methods=['POST'])
@login_required
def client_pay_booking(booking_id):
    user = current_user()
    payment_method = request.form.get('payment_method', '').strip()
    promo_id = request.form.get('promo_id', type=int)

    if payment_method not in ('bank', 'bonus'):
        return jsonify({'error': 'Выберите способ оплаты'}), 400

    conn = get_db()
    booking = conn.execute("""
        SELECT b.*, s.price as session_price, s.date, s.time
        FROM bookings b
        JOIN sessions s ON s.id = b.session_id
        WHERE b.id=? AND b.user_id=?
    """, (booking_id, user['id'])).fetchone()

    if not booking:
        conn.close()
        return jsonify({'error': 'Бронирование не найдено'}), 404

    if booking['status'] != 'booked':
        conn.close()
        return jsonify({'error': 'Этот билет уже нельзя оплатить'}), 400

    now_date = date.today().isoformat()
    now_time = datetime.now().strftime('%H:%M')
    if booking['date'] < now_date or (booking['date'] == now_date and booking['time'] < now_time):
        conn.close()
        return jsonify({'error': 'Сеанс уже прошёл'}), 400

    base_price = float(booking['session_price'] or booking['final_price'] or 0)
    discount = 0
    if promo_id:
        promo = conn.execute('SELECT discount FROM promotions WHERE id=?', (promo_id,)).fetchone()
        if promo:
            discount = int(promo['discount'] or 0)
        else:
            promo_id = None

    final_price = round(base_price * (1 - discount / 100), 2)

    if payment_method == 'bonus':
        card = conn.execute('SELECT * FROM loyalty_cards WHERE user_id=?', (user['id'],)).fetchone()
        if not card:
            conn.close()
            return jsonify({'error': 'У вас нет бонусной карты'}), 400
        if int(card['bonus_balance'] or 0) < int(round(final_price)):
            conn.close()
            return jsonify({'error': 'Недостаточно бонусов на карте'}), 400

    conn.execute("""
        UPDATE bookings
        SET status='paid', payment_method=?, promo_id=?, final_price=?
        WHERE id=?
    """, (payment_method, promo_id, final_price, booking_id))

    if payment_method == 'bonus':
        ok, err = spend_bonuses_for_booking(conn, user['id'], booking_id, final_price)
        if not ok:
            conn.close()
            return jsonify({'error': err}), 400
        award_bonus_for_booking(conn, booking_id)

    conn.commit()
    conn.close()
    send_paid_tickets_email(user['email'], [booking_id])
    return jsonify({
        'ok': True,
        'message': 'Билеты оплачены и отправлены на вашу почту'
    })

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

    capacity = int(capacity)
    conn = get_db()  # СНАЧАЛА открываем соединение

    old = conn.execute('SELECT capacity, rows, seats_per_row, status FROM halls WHERE id=?', (hall_id,)).fetchone()
    print(f"OLD: {old['capacity']}, NEW: {capacity}")

    if status == 'closed' and old['status'] != 'closed':
        today = date.today().isoformat()
        now_time = datetime.now().strftime('%H:%M')
        upcoming_sessions = conn.execute('''
                SELECT id FROM sessions
                WHERE hall_id=? AND (date > ? OR (date = ? AND time > ?))
            ''', (hall_id, today, today, now_time)).fetchall()
        for s in upcoming_sessions:
            conn.execute("UPDATE bookings SET status='cancelled' WHERE session_id=? AND status != 'cancelled'",
                         (s['id'],))
            conn.execute('DELETE FROM sessions WHERE id=?', (s['id'],))

    if old['capacity'] != capacity:
        import math
        rows = math.ceil(math.sqrt(capacity * 2 / 3))
        seats_per_row = math.ceil(capacity / rows)

        conn.execute('DELETE FROM bookings WHERE seat_id IN (SELECT id FROM seats WHERE hall_id=?)', (hall_id,))
        conn.execute('DELETE FROM seats WHERE hall_id=?', (hall_id,))

        seats_created = 0
        for row in range(1, rows + 1):
            seats_in_row = seats_per_row if seats_created + seats_per_row <= capacity else capacity - seats_created
            for seat in range(1, seats_in_row + 1):
                conn.execute('INSERT INTO seats (hall_id, row_num, seat_num) VALUES (?,?,?)',
                             (hall_id, row, seat))
            seats_created += seats_in_row

        conn.execute('UPDATE halls SET name=?, status=?, capacity=?, format=?, rows=?, seats_per_row=? WHERE id=?',
                     (name, status, capacity, format, rows, seats_per_row, hall_id))
    else:
        conn.execute('UPDATE halls SET name=?, status=?, format=? WHERE id=?',
                     (name, status, format, hall_id))

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
    hall = conn.execute('SELECT status FROM halls WHERE id=?', (hall_id,)).fetchone()
    if not hall or hall['status'] == 'closed':
        conn.close()
        return redirect(url_for('personal') + '?tab=sessions')

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