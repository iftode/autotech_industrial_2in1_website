from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from flask import Flask, flash, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / 'database' / 'store.db'
UPLOAD_FOLDER = BASE_DIR / 'static' / 'images'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}

app = Flask(__name__)
app.secret_key = 'magazin-automatizari-secret-key'
app.config['UPLOAD_FOLDER'] = str(UPLOAD_FOLDER)

ADMIN_USER = 'admin'
ADMIN_PASS = 'admin123'

PAYMENT_METHODS = {
    'ramburs': 'Plată ramburs',
    'card': 'Card online',
    'transfer': 'Transfer bancar',
}


def get_db() -> sqlite3.Connection:
    if 'db' not in g:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db


@app.teardown_appcontext
def close_db(_: Any) -> None:
    db = g.pop('db', None)
    if db is not None:
        db.close()


def column_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    rows = conn.execute(f'PRAGMA table_info({table_name})').fetchall()
    return any(row[1] == column_name for row in rows)


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.executescript(
        '''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            phone TEXT,
            address TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            sku TEXT UNIQUE,
            price REAL NOT NULL,
            stock INTEGER NOT NULL DEFAULT 0,
            image TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            featured INTEGER NOT NULL DEFAULT 0,
            specs TEXT,
            FOREIGN KEY(category_id) REFERENCES categories(id)
        );

        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL,
            customer_email TEXT NOT NULL,
            address TEXT NOT NULL,
            phone TEXT,
            total REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'Nouă',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            qty INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            line_total REAL NOT NULL,
            FOREIGN KEY(order_id) REFERENCES orders(id),
            FOREIGN KEY(product_id) REFERENCES products(id)
        );

        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL,
            company TEXT,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS shipments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL UNIQUE,
            courier TEXT NOT NULL,
            awb TEXT NOT NULL,
            tracking_url TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'AWB generat',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(order_id) REFERENCES orders(id)
        );

        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL UNIQUE,
            invoice_number TEXT NOT NULL UNIQUE,
            total REAL NOT NULL,
            created_by TEXT NOT NULL DEFAULT 'admin',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(order_id) REFERENCES orders(id)
        );

        CREATE TABLE IF NOT EXISTS returns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL UNIQUE,
            reason TEXT,
            status TEXT NOT NULL DEFAULT 'Cerere trimisă',
            admin_note TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT,
            FOREIGN KEY(order_id) REFERENCES orders(id)
        );
        '''
    )

    if not column_exists(conn, 'orders', 'user_id'):
        cur.execute('ALTER TABLE orders ADD COLUMN user_id INTEGER')

    if not column_exists(conn, 'orders', 'payment_method'):
        cur.execute("ALTER TABLE orders ADD COLUMN payment_method TEXT NOT NULL DEFAULT 'ramburs'")

    if not column_exists(conn, 'orders', 'card_holder'):
        cur.execute("ALTER TABLE orders ADD COLUMN card_holder TEXT")

    if not column_exists(conn, 'orders', 'card_last4'):
        cur.execute("ALTER TABLE orders ADD COLUMN card_last4 TEXT")

    category_count = cur.execute('SELECT COUNT(*) FROM categories').fetchone()[0]
    if category_count == 0:
        categories = [
            ('PLC-uri', 'plc-uri'),
            ('Senzori industriali', 'senzori-industriali'),
            ('Panouri HMI', 'panouri-hmi'),
            ('Acționări și motoare', 'actionari-si-motoare'),
            ('Control și monitorizare', 'control-si-monitorizare'),
        ]
        cur.executemany('INSERT INTO categories (name, slug) VALUES (?, ?)', categories)

    product_count = cur.execute('SELECT COUNT(*) FROM products').fetchone()[0]
    if product_count == 0:
        ids = {row[1]: row[0] for row in cur.execute('SELECT id, slug FROM categories').fetchall()}
        products = [
            (
                ids['plc-uri'],
                'PLC Siemens S7-1200',
                'Controler programabil compact pentru linii de producție, automatizări și procese industriale.',
                'PLC-S7-1200',
                1899.99,
                12,
                'plc.jpg',
                1,
                1,
                'CPU compactă, comunicație PROFINET, extensibilă cu module I/O'
            ),
            (
                ids['senzori-industriali'],
                'Senzor inductiv M12',
                'Senzor de proximitate robust pentru detectarea pieselor metalice în medii industriale.',
                'SEN-M12-IND',
                149.99,
                40,
                'si.jpg',
                1,
                1,
                'Distanță detecție 4 mm, alimentare 10-30V DC, IP67'
            ),
            (
                ids['panouri-hmi'],
                'Panou HMI 7 inch',
                'Interfață operator tactilă pentru monitorizare procese, alarme și control parametri.',
                'HMI-7-PRO',
                1249.00,
                8,
                'cf.jpg',
                1,
                1,
                'Ecran tactil 7”, conectivitate Modbus / Ethernet'
            ),
            (
                ids['actionari-si-motoare'],
                'Servo drive industrial',
                'Soluție performantă pentru poziționare precisă și control de mișcare în instalații automate.',
                'SERVO-450',
                2199.50,
                5,
                'aa.jpg',
                1,
                0,
                'Control viteză și poziție, răspuns rapid, eficiență ridicată'
            ),
            (
                ids['control-si-monitorizare'],
                'Modul I/O pentru monitorizare',
                'Extensie pentru citire senzori și comandă ieșiri digitale în sisteme SCADA și PLC.',
                'IO-MOD-16',
                579.00,
                16,
                'plc.jpg',
                1,
                0,
                '8 intrări digitale, 8 ieșiri digitale, montaj pe șină DIN'
            ),
        ]
        cur.executemany(
            '''
            INSERT INTO products (
                category_id, name, description, sku, price, stock, image, is_active, featured, specs
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            products,
        )

    conn.commit()
    conn.close()


def cleanup_old_orders() -> None:
    conn = get_db()
    cursor = conn.cursor()

    now = datetime.now()
    limit_30_days = (now - timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
    limit_return_days = (now - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')

    old_orders = cursor.execute(
        '''
        SELECT id
        FROM orders
        WHERE created_at < ?
        ''',
        (limit_30_days,),
    ).fetchall()

    for row in old_orders:
        order_id = row['id']
        cursor.execute('DELETE FROM order_items WHERE order_id = ?', (order_id,))
        cursor.execute('DELETE FROM orders WHERE id = ?', (order_id,))

    returned_orders = cursor.execute(
        '''
        SELECT id
        FROM orders
        WHERE status = 'Retur' AND created_at < ?
        ''',
        (limit_return_days,),
    ).fetchall()

    for row in returned_orders:
        order_id = row['id']
        cursor.execute('DELETE FROM order_items WHERE order_id = ?', (order_id,))
        cursor.execute('DELETE FROM orders WHERE id = ?', (order_id,))

    conn.commit()


@app.before_request
def before_request() -> None:
    cleanup_old_orders()


def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_cart() -> dict[str, int]:
    cart = session.get('cart')
    if not isinstance(cart, dict):
        cart = {}
        session['cart'] = cart
    return cart


def cart_count() -> int:
    return sum(int(v) for v in get_cart().values())


def is_admin() -> bool:
    return session.get('admin_logged_in') is True


def current_user() -> sqlite3.Row | None:
    user_id = session.get('user_id')
    if not user_id:
        return None
    return get_db().execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()


def user_guard():
    if not session.get('user_id'):
        flash('Autentifică-te pentru a accesa contul tău.', 'warning')
        return redirect(url_for('login'))
    return None


def admin_guard():
    if not is_admin():
        flash('Autentifică-te pentru a accesa panoul de administrare.', 'warning')
        return redirect(url_for('admin_login'))
    return None


def fetch_categories() -> list[sqlite3.Row]:
    return get_db().execute('SELECT id, name, slug FROM categories ORDER BY name').fetchall()


def extract_order_id(message: str) -> int | None:
    match = re.search(r'(?:comanda|comandă|order)\s*#?\s*(\d+)', message, re.IGNORECASE)
    if match:
        return int(match.group(1))

    numbers = re.findall(r'\b\d+\b', message)
    if len(numbers) == 1:
        return int(numbers[0])

    return None


def extract_email(message: str) -> str | None:
    match = re.search(r'([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})', message)
    if match:
        return match.group(1).strip().lower()
    return None


def payment_label(payment_method: str | None) -> str:
    return PAYMENT_METHODS.get(payment_method or 'ramburs', 'Plată ramburs')


def generate_awb(courier: str, order_id: int) -> tuple[str, str]:
    courier_key = (courier or 'fan').lower().strip()
    prefix = 'FAN' if courier_key == 'fan' else 'SDY'
    awb = f'{prefix}-{order_id:06d}-{uuid4().hex[:6].upper()}'
    if courier_key == 'sameday':
        return awb, f'https://sameday.ro/awb-tracking?awb={awb}'
    return awb, f'https://www.fancourier.ro/awb-tracking/?xawb={awb}'


def next_invoice_number(db: sqlite3.Connection) -> str:
    row = db.execute('SELECT COUNT(*) AS total FROM invoices').fetchone()
    number = int(row['total'] if row else 0) + 1
    return f'AUT-{number:06d}'


def clean_card_number(card_number: str) -> str:
    return re.sub(r'\D', '', card_number or '')


def valid_expiry(expiry: str) -> bool:
    return bool(re.fullmatch(r'(0[1-9]|1[0-2])\/\d{2}', expiry.strip()))


def valid_cvv(cvv: str) -> bool:
    return bool(re.fullmatch(r'\d{3,4}', cvv.strip()))


def get_order_details(order_id: int, customer_email: str) -> dict[str, Any] | None:
    db = get_db()
    order = db.execute(
        '''
        SELECT *
        FROM orders
        WHERE id = ? AND lower(customer_email) = lower(?)
        ''',
        (order_id, customer_email),
    ).fetchone()

    if not order:
        return None

    items = db.execute(
        '''
        SELECT oi.qty, oi.unit_price, oi.line_total, p.name
        FROM order_items oi
        JOIN products p ON p.id = oi.product_id
        WHERE oi.order_id = ?
        ORDER BY oi.id ASC
        ''',
        (order_id,),
    ).fetchall()

    return {
        'id': order['id'],
        'customer_name': order['customer_name'],
        'customer_email': order['customer_email'],
        'address': order['address'],
        'phone': order['phone'],
        'total': float(order['total']),
        'status': order['status'],
        'created_at': order['created_at'],
        'payment_method': order['payment_method'],
        'payment_label': payment_label(order['payment_method']),
        'card_holder': order['card_holder'],
        'card_last4': order['card_last4'],
        'items': [
            {
                'name': item['name'],
                'qty': int(item['qty']),
                'unit_price': float(item['unit_price']),
                'line_total': float(item['line_total']),
            }
            for item in items
        ],
    }


def build_order_status_reply(order_data: dict[str, Any]) -> str:
    items_text = ', '.join([f"{item['name']} x{item['qty']}" for item in order_data['items']]) or 'fără produse'
    card_info = ''
    if order_data['payment_method'] == 'card' and order_data['card_last4']:
        card_info = f" Plata simulată a fost înregistrată cu card terminat în {order_data['card_last4']}."
    return (
        f"Am găsit comanda #{order_data['id']}. "
        f"Statusul actual este: {order_data['status']}. "
        f"Metoda de plată: {order_data['payment_label']}. "
        f"Data înregistrării: {order_data['created_at']}. "
        f"Produse: {items_text}. "
        f"Valoare totală: {order_data['total']:.2f} lei."
        f"{card_info}"
    )


def chatbot_reply(message: str) -> str:
    text = (message or '').strip()
    lower = text.lower()

    if not text:
        return 'Te rog să scrii un mesaj. De exemplu: „Care este statusul comenzii 1, email test@test.com?”'

    greetings = ['salut', 'buna', 'bună', 'hello', 'hey']
    if any(word in lower for word in greetings):
        return (
            'Salut! Sunt asistentul AutoTech Industrial. '
            'Te pot ajuta cu statusul comenzii, livrare, retur, contact, metode de plată sau informații despre produse.'
        )

    if any(word in lower for word in ['plata', 'plată', 'card', 'ramburs', 'transfer']):
        return (
            'Metodele de plată disponibile sunt: Plată ramburs, Card online și Transfer bancar. '
            'La plata cu cardul se completează date fictive doar pentru simularea procesului de plată.'
        )

    if any(word in lower for word in ['status', 'comanda', 'comandă', 'order']):
        order_id = extract_order_id(text)
        email = extract_email(text)

        if order_id and email:
            order_data = get_order_details(order_id, email)
            if order_data:
                return build_order_status_reply(order_data)
            return (
                'Nu am găsit o comandă cu datele introduse. '
                'Verifică numărul comenzii și emailul folosit la plasare.'
            )

        return (
            'Pentru verificarea comenzii, te rog să-mi trimiți mesajul în formatul: '
            '„Status comandă 1, email nume@exemplu.com”.'
        )

    if any(word in lower for word in ['livrare', 'transport', 'cand ajunge', 'când ajunge', 'curier']):
        return (
            'Livrarea se realizează în funcție de disponibilitatea produselor și confirmarea comenzii. '
            'Pentru verificarea unei comenzi existente, trimite: „Status comandă NUMĂR, email ADRESA_TA”.'
        )

    if any(word in lower for word in ['retur', 'returnare', 'anulare', 'anulez']):
        return (
            'Pentru retur sau anulare, te rugăm să ne contactezi din pagina Contact și să menționezi '
            'numărul comenzii, numele și emailul folosit la plasare.'
        )

    if any(word in lower for word in ['contact', 'telefon', 'email', 'suport', 'program']):
        return (
            'Ne poți contacta din pagina Contact a site-ului. '
            'Poți trimite un mesaj direct din formularul de contact pentru ofertă, suport sau informații comerciale.'
        )

    if any(word in lower for word in ['produs', 'produse', 'catalog', 'stoc', 'plc', 'senzor', 'hmi', 'servo']):
        db = get_db()
        products = db.execute(
            '''
            SELECT name, stock, price
            FROM products
            WHERE is_active = 1
            ORDER BY featured DESC, id DESC
            LIMIT 5
            '''
        ).fetchall()

        if not products:
            return 'Momentan nu există produse active în catalog.'

        lines = [
            f"{row['name']} - {float(row['price']):.2f} lei - stoc {int(row['stock'])}"
            for row in products
        ]
        return 'Produse disponibile în acest moment: ' + '; '.join(lines) + '.'

    return (
        'Pot să te ajut cu: status comandă, livrare, retur, metode de plată, contact și produse disponibile. '
        'Exemplu: „Status comandă 1, email client@exemplu.com”.'
    )


@app.context_processor
def inject_globals() -> dict[str, Any]:
    return {
        'cart_count': cart_count(),
        'logged_user': current_user(),
    }


@app.route('/')
def index():
    db = get_db()
    featured = db.execute(
        '''
        SELECT p.*, c.name AS category_name, c.slug AS category_slug
        FROM products p
        JOIN categories c ON c.id = p.category_id
        WHERE p.is_active = 1 AND p.featured = 1
        ORDER BY p.id DESC
        LIMIT 3
        '''
    ).fetchall()
    latest = db.execute(
        '''
        SELECT p.*, c.name AS category_name
        FROM products p
        JOIN categories c ON c.id = p.category_id
        WHERE p.is_active = 1
        ORDER BY p.id DESC
        LIMIT 6
        '''
    ).fetchall()
    stats = {
        'products': db.execute('SELECT COUNT(*) FROM products WHERE is_active = 1').fetchone()[0],
        'categories': db.execute('SELECT COUNT(*) FROM categories').fetchone()[0],
        'orders': db.execute('SELECT COUNT(*) FROM orders').fetchone()[0],
    }
    return render_template('index.html', featured=featured, latest=latest, stats=stats)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if session.get('user_id'):
        return redirect(url_for('account'))

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()
        phone = request.form.get('phone', '').strip()
        address = request.form.get('address', '').strip()

        if not full_name or not email or not password:
            flash('Completează numele, emailul și parola.', 'danger')
            return redirect(url_for('register'))

        db = get_db()
        existing = db.execute('SELECT id FROM users WHERE lower(email) = lower(?)', (email,)).fetchone()
        if existing:
            flash('Există deja un cont cu acest email.', 'warning')
            return redirect(url_for('register'))

        db.execute(
            '''
            INSERT INTO users (full_name, email, password_hash, phone, address)
            VALUES (?, ?, ?, ?, ?)
            ''',
            (full_name, email, generate_password_hash(password), phone, address),
        )
        db.commit()

        user = db.execute('SELECT * FROM users WHERE lower(email) = lower(?)', (email,)).fetchone()
        session['user_id'] = user['id']
        flash('Contul a fost creat cu succes.', 'success')
        return redirect(url_for('account'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_id'):
        return redirect(url_for('account'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()

        db = get_db()
        user = db.execute('SELECT * FROM users WHERE lower(email) = lower(?)', (email,)).fetchone()

        if not user or not check_password_hash(user['password_hash'], password):
            flash('Email sau parolă incorecte.', 'danger')
            return redirect(url_for('login'))

        session['user_id'] = user['id']
        flash('Autentificare reușită.', 'success')
        return redirect(url_for('account'))

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('Te-ai delogat din contul de utilizator.', 'info')
    return redirect(url_for('index'))


@app.route('/contul-meu')
def account():
    guard = user_guard()
    if guard:
        return guard

    user = current_user()
    db = get_db()
    orders = db.execute(
        '''
        SELECT *
        FROM orders
        WHERE user_id = ? OR lower(customer_email) = lower(?)
        ORDER BY id DESC
        ''',
        (user['id'], user['email']),
    ).fetchall()

    return render_template('account.html', user=user, orders=orders, payment_label=payment_label)

@app.route('/account/order/<int:order_id>/return', methods=['POST'])
def request_order_return(order_id: int):
    guard = user_guard()
    if guard:
        return guard

    user = current_user()
    db = get_db()

    order = db.execute(
        '''
        SELECT *
        FROM orders
        WHERE id = ? AND (user_id = ? OR lower(customer_email) = lower(?))
        ''',
        (order_id, user['id'], user['email']),
    ).fetchone()

    if not order:
        flash('Comanda nu a fost găsită în contul tău.', 'danger')
        return redirect(url_for('account'))

    existing_return = db.execute('SELECT id FROM returns WHERE order_id = ?', (order_id,)).fetchone()
    if existing_return:
        flash('Returul a fost deja solicitat pentru această comandă.', 'warning')
        return redirect(url_for('account'))

    reason = request.form.get('reason', '').strip()
    db.execute('INSERT INTO returns (order_id, reason) VALUES (?, ?)', (order_id, reason))
    db.execute("UPDATE orders SET status = 'Retur solicitat' WHERE id = ?", (order_id,))
    db.commit()

    flash('Solicitarea de retur a fost înregistrată.', 'success')
    return redirect(url_for('account'))

@app.route('/produse')
def products():
    db = get_db()
    category_slug = request.args.get('categorie', '').strip()
    query = request.args.get('q', '').strip()

    sql = '''
        SELECT p.*, c.name AS category_name, c.slug AS category_slug
        FROM products p
        JOIN categories c ON c.id = p.category_id
        WHERE p.is_active = 1
    '''
    params: list[Any] = []

    if category_slug:
        sql += ' AND c.slug = ?'
        params.append(category_slug)

    if query:
        sql += ' AND (p.name LIKE ? OR p.description LIKE ? OR IFNULL(p.specs, "") LIKE ?)'
        like = f'%{query}%'
        params.extend([like, like, like])

    sql += ' ORDER BY p.id DESC'
    items = db.execute(sql, params).fetchall()
    categories = fetch_categories()
    return render_template('products.html', products=items, categories=categories, current_category=category_slug, search=query)


@app.route('/produs/<int:product_id>')
def product_detail(product_id: int):
    db = get_db()
    product = db.execute(
        '''
        SELECT p.*, c.name AS category_name, c.slug AS category_slug
        FROM products p
        JOIN categories c ON c.id = p.category_id
        WHERE p.id = ?
        ''',
        (product_id,),
    ).fetchone()
    if not product:
        flash('Produsul nu există.', 'danger')
        return redirect(url_for('products'))

    related = db.execute(
        '''
        SELECT id, name, price, image
        FROM products
        WHERE is_active = 1 AND category_id = ? AND id != ?
        ORDER BY id DESC
        LIMIT 3
        ''',
        (product['category_id'], product_id),
    ).fetchall()
    return render_template('product_detail.html', product=product, related=related)


@app.route('/despre')
def about():
    return render_template('about.html')


@app.route('/contact', methods=['GET', 'POST'])
def contact():
    user = current_user()

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        company = request.form.get('company', '').strip()
        message = request.form.get('message', '').strip()

        if not full_name or not email or not message:
            flash('Completează numele, emailul și mesajul.', 'danger')
            return redirect(url_for('contact'))

        db = get_db()
        db.execute(
            'INSERT INTO contacts (full_name, email, company, message) VALUES (?, ?, ?, ?)',
            (full_name, email, company, message),
        )
        db.commit()
        flash('Mesajul a fost trimis cu succes. Te vom contacta în cel mai scurt timp.', 'success')
        return redirect(url_for('contact'))

    return render_template('contact.html', user=user)


@app.route('/add/<int:product_id>')
def add_to_cart(product_id: int):
    db = get_db()
    product = db.execute('SELECT id, is_active FROM products WHERE id = ?', (product_id,)).fetchone()
    if not product or not product['is_active']:
        flash('Produsul selectat nu este disponibil.', 'danger')
        return redirect(url_for('products'))

    cart = get_cart()
    key = str(product_id)
    cart[key] = int(cart.get(key, 0)) + 1
    session['cart'] = cart
    session.modified = True
    flash('Produsul a fost adăugat în coș.', 'success')
    return redirect(request.referrer or url_for('products'))


@app.route('/cart')
def view_cart():
    db = get_db()
    cart = get_cart()
    ids = [int(pid) for pid in cart.keys()]
    items: list[dict[str, Any]] = []
    total = 0.0

    if ids:
        placeholders = ','.join('?' for _ in ids)
        products_map = {
            row['id']: row
            for row in db.execute(
                f'SELECT id, name, price, image, stock FROM products WHERE id IN ({placeholders})', ids
            ).fetchall()
        }
        for pid, qty in cart.items():
            product = products_map.get(int(pid))
            if not product:
                continue
            line_total = float(product['price']) * int(qty)
            total += line_total
            items.append(
                {
                    'id': product['id'],
                    'name': product['name'],
                    'price': float(product['price']),
                    'qty': int(qty),
                    'image': product['image'],
                    'stock': int(product['stock']),
                    'line_total': line_total,
                }
            )

    return render_template('cart.html', items=items, total=total)


@app.route('/cart/update/<int:product_id>', methods=['POST'])
def update_cart_qty(product_id: int):
    action = request.form.get('action', '')
    cart = get_cart()
    key = str(product_id)
    if key not in cart:
        return redirect(url_for('view_cart'))

    qty = int(cart[key])
    if action == 'inc':
        cart[key] = qty + 1
    elif action == 'dec':
        if qty <= 1:
            cart.pop(key, None)
        else:
            cart[key] = qty - 1
    session['cart'] = cart
    session.modified = True
    return redirect(url_for('view_cart'))


@app.route('/cart/remove/<int:product_id>', methods=['POST'])
def remove_from_cart(product_id: int):
    cart = get_cart()
    cart.pop(str(product_id), None)
    session['cart'] = cart
    session.modified = True
    flash('Produsul a fost eliminat din coș.', 'info')
    return redirect(url_for('view_cart'))


@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    db = get_db()
    user = current_user()
    cart = get_cart()

    if not cart:
        flash('Coșul este gol.', 'warning')
        return redirect(url_for('products'))

    ids = [int(pid) for pid in cart.keys()]
    placeholders = ','.join('?' for _ in ids)
    products_map = {
        row['id']: row
        for row in db.execute(
            f'SELECT id, name, price, stock FROM products WHERE id IN ({placeholders})', ids
        ).fetchall()
    }

    items = []
    total = 0.0
    for pid_str, qty in cart.items():
        product = products_map.get(int(pid_str))
        if not product:
            continue
        line_total = float(product['price']) * int(qty)
        total += line_total
        items.append({'product': product, 'qty': int(qty), 'line_total': line_total})

    if request.method == 'POST':
        customer_name = request.form.get('customer_name', '').strip()
        customer_email = request.form.get('customer_email', '').strip()
        address = request.form.get('address', '').strip()
        phone = request.form.get('phone', '').strip()
        payment_method = request.form.get('payment_method', 'ramburs').strip()

        card_holder = request.form.get('card_holder', '').strip()
        card_number = clean_card_number(request.form.get('card_number', ''))
        card_expiry = request.form.get('card_expiry', '').strip()
        card_cvv = request.form.get('card_cvv', '').strip()

        if not customer_name or not customer_email or not address:
            flash('Completează numele, emailul și adresa.', 'danger')
            return redirect(url_for('checkout'))

        if payment_method not in PAYMENT_METHODS:
            flash('Alege o metodă de plată validă.', 'danger')
            return redirect(url_for('checkout'))

        card_last4 = None

        if payment_method == 'card':
            if not card_holder or not card_number or not card_expiry or not card_cvv:
                flash('Pentru plata cu cardul, completează toate datele cardului.', 'danger')
                return redirect(url_for('checkout'))

            if len(card_number) < 12 or len(card_number) > 19:
                flash('Numărul cardului fictiv trebuie să conțină între 12 și 19 cifre.', 'danger')
                return redirect(url_for('checkout'))

            if not valid_expiry(card_expiry):
                flash('Data expirării trebuie să fie în format MM/YY.', 'danger')
                return redirect(url_for('checkout'))

            if not valid_cvv(card_cvv):
                flash('CVV-ul trebuie să conțină 3 sau 4 cifre.', 'danger')
                return redirect(url_for('checkout'))

            card_last4 = card_number[-4:]

        for entry in items:
            if int(entry['product']['stock']) < int(entry['qty']):
                flash(f"Stoc insuficient pentru produsul: {entry['product']['name']}", 'danger')
                return redirect(url_for('view_cart'))

        cur = db.cursor()
        cur.execute(
            '''
            INSERT INTO orders (
                customer_name, customer_email, address, phone, total, status, user_id, payment_method, card_holder, card_last4
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                customer_name,
                customer_email,
                address,
                phone,
                total,
                'Nouă',
                user['id'] if user else None,
                payment_method,
                card_holder if payment_method == 'card' else None,
                card_last4,
            ),
        )
        order_id = cur.lastrowid

        for entry in items:
            product = entry['product']
            qty = int(entry['qty'])
            cur.execute(
                'INSERT INTO order_items (order_id, product_id, qty, unit_price, line_total) VALUES (?, ?, ?, ?, ?)',
                (order_id, product['id'], qty, float(product['price']), entry['line_total']),
            )
            cur.execute('UPDATE products SET stock = stock - ? WHERE id = ?', (qty, product['id']))

        db.commit()
        session['cart'] = {}
        session.modified = True
        return redirect(url_for('order_success', order_id=order_id))

    return render_template(
        'checkout.html',
        items=items,
        total=total,
        user=user,
        payment_methods=PAYMENT_METHODS,
    )


@app.route('/order-success/<int:order_id>')
def order_success(order_id: int):
    order = get_db().execute('SELECT * FROM orders WHERE id = ?', (order_id,)).fetchone()
    if not order:
        flash('Comanda nu a fost găsită.', 'warning')
        return redirect(url_for('index'))
    return render_template('success.html', order=order, payment_label=payment_label)


@app.route('/api/chat', methods=['POST'])
def api_chat():
    data = request.get_json(silent=True) or {}
    message = str(data.get('message', '')).strip()
    response_text = chatbot_reply(message)
    return jsonify({'reply': response_text})


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        if username == ADMIN_USER and password == ADMIN_PASS:
            session['admin_logged_in'] = True
            flash('Autentificare reușită.', 'success')
            return redirect(url_for('admin_dashboard'))
        flash('Date de autentificare incorecte.', 'danger')
    return render_template('admin/login.html')


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    flash('Te-ai delogat din panoul de administrare.', 'info')
    return redirect(url_for('admin_login'))


@app.route('/admin')
def admin_dashboard():
    guard = admin_guard()
    if guard:
        return guard
    db = get_db()
    stats = {
        'products': db.execute('SELECT COUNT(*) FROM products').fetchone()[0],
        'categories': db.execute('SELECT COUNT(*) FROM categories').fetchone()[0],
        'orders': db.execute('SELECT COUNT(*) FROM orders').fetchone()[0],
        'messages': db.execute('SELECT COUNT(*) FROM contacts').fetchone()[0],
    }
    recent_orders = db.execute('SELECT * FROM orders ORDER BY id DESC LIMIT 5').fetchall()
    return render_template('admin/dashboard.html', stats=stats, recent_orders=recent_orders, payment_label=payment_label)


@app.route('/admin/categories')
def admin_categories():
    guard = admin_guard()
    if guard:
        return guard
    categories = fetch_categories()
    return render_template('admin/categories.html', categories=categories)


@app.route('/admin/categories/new', methods=['GET', 'POST'])
def admin_category_new():
    guard = admin_guard()
    if guard:
        return guard
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        slug = request.form.get('slug', '').strip()
        if not name or not slug:
            flash('Completează numele și slug-ul.', 'danger')
            return redirect(url_for('admin_category_new'))
        db = get_db()
        try:
            db.execute('INSERT INTO categories (name, slug) VALUES (?, ?)', (name, slug))
            db.commit()
            flash('Categoria a fost adăugată.', 'success')
            return redirect(url_for('admin_categories'))
        except sqlite3.IntegrityError:
            flash('Slug-ul există deja.', 'danger')
    return render_template('admin/category_form.html', category=None, mode='new')


@app.route('/admin/categories/edit/<int:cat_id>', methods=['GET', 'POST'])
def admin_category_edit(cat_id: int):
    guard = admin_guard()
    if guard:
        return guard
    db = get_db()
    category = db.execute('SELECT * FROM categories WHERE id = ?', (cat_id,)).fetchone()
    if not category:
        flash('Categoria nu există.', 'danger')
        return redirect(url_for('admin_categories'))
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        slug = request.form.get('slug', '').strip()
        if not name or not slug:
            flash('Completează numele și slug-ul.', 'danger')
            return redirect(url_for('admin_category_edit', cat_id=cat_id))
        try:
            db.execute('UPDATE categories SET name = ?, slug = ? WHERE id = ?', (name, slug, cat_id))
            db.commit()
            flash('Categoria a fost actualizată.', 'success')
            return redirect(url_for('admin_categories'))
        except sqlite3.IntegrityError:
            flash('Slug-ul există deja.', 'danger')
    return render_template('admin/category_form.html', category=category, mode='edit')


@app.route('/admin/categories/delete/<int:cat_id>', methods=['POST'])
def admin_category_delete(cat_id: int):
    guard = admin_guard()
    if guard:
        return guard
    db = get_db()
    products_using = db.execute('SELECT COUNT(*) FROM products WHERE category_id = ?', (cat_id,)).fetchone()[0]
    if products_using > 0:
        flash('Categoria nu poate fi ștearsă deoarece există produse asociate.', 'warning')
        return redirect(url_for('admin_categories'))
    db.execute('DELETE FROM categories WHERE id = ?', (cat_id,))
    db.commit()
    flash('Categoria a fost ștearsă.', 'success')
    return redirect(url_for('admin_categories'))


@app.route('/admin/products')
def admin_products():
    guard = admin_guard()
    if guard:
        return guard
    items = get_db().execute(
        '''
        SELECT p.*, c.name AS category_name
        FROM products p
        JOIN categories c ON c.id = p.category_id
        ORDER BY p.id DESC
        '''
    ).fetchall()
    return render_template('admin/products.html', products=items)


@app.route('/admin/products/new', methods=['GET', 'POST'])
def admin_product_new():
    guard = admin_guard()
    if guard:
        return guard
    categories = fetch_categories()
    if request.method == 'POST':
        return save_product_form(categories)
    return render_template('admin/product_form.html', product=None, categories=categories, mode='new')


@app.route('/admin/products/edit/<int:product_id>', methods=['GET', 'POST'])
def admin_product_edit(product_id: int):
    guard = admin_guard()
    if guard:
        return guard
    db = get_db()
    categories = fetch_categories()
    product = db.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
    if not product:
        flash('Produsul nu există.', 'danger')
        return redirect(url_for('admin_products'))
    if request.method == 'POST':
        return save_product_form(categories, product)
    return render_template('admin/product_form.html', product=product, categories=categories, mode='edit')


def save_product_form(categories: list[sqlite3.Row], product: sqlite3.Row | None = None):
    db = get_db()
    category_id = request.form.get('category_id', '').strip()
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    sku = request.form.get('sku', '').strip() or None
    price = request.form.get('price', '').strip()
    stock = request.form.get('stock', '').strip()
    specs = request.form.get('specs', '').strip()
    is_active = 1 if request.form.get('is_active') == 'on' else 0
    featured = 1 if request.form.get('featured') == 'on' else 0

    if not category_id or not name or not price or not stock:
        flash('Completează câmpurile obligatorii: categorie, nume, preț și stoc.', 'danger')
        endpoint = 'admin_product_edit' if product else 'admin_product_new'
        kwargs = {'product_id': product['id']} if product else {}
        return redirect(url_for(endpoint, **kwargs))

    image_name = product['image'] if product else None
    file = request.files.get('image')
    if file and file.filename:
        if not allowed_file(file.filename):
            flash('Format imagine neacceptat.', 'danger')
            endpoint = 'admin_product_edit' if product else 'admin_product_new'
            kwargs = {'product_id': product['id']} if product else {}
            return redirect(url_for(endpoint, **kwargs))
        filename = secure_filename(file.filename)
        ext = filename.rsplit('.', 1)[1].lower()
        unique_name = f'{uuid4().hex}.{ext}'
        file.save(UPLOAD_FOLDER / unique_name)
        image_name = unique_name

    try:
        if product:
            db.execute(
                '''
                UPDATE products
                SET category_id = ?, name = ?, description = ?, sku = ?, price = ?, stock = ?, image = ?,
                    is_active = ?, featured = ?, specs = ?
                WHERE id = ?
                ''',
                (category_id, name, description, sku, float(price), int(stock), image_name, is_active, featured, specs, product['id']),
            )
            flash('Produsul a fost actualizat.', 'success')
        else:
            db.execute(
                '''
                INSERT INTO products (category_id, name, description, sku, price, stock, image, is_active, featured, specs)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (category_id, name, description, sku, float(price), int(stock), image_name, is_active, featured, specs),
            )
            flash('Produsul a fost adăugat.', 'success')
        db.commit()
    except sqlite3.IntegrityError:
        flash('SKU-ul există deja. Folosește un cod unic.', 'danger')
        endpoint = 'admin_product_edit' if product else 'admin_product_new'
        kwargs = {'product_id': product['id']} if product else {}
        return redirect(url_for(endpoint, **kwargs))

    return redirect(url_for('admin_products'))


@app.route('/admin/products/delete/<int:product_id>', methods=['POST'])
def admin_product_delete(product_id: int):
    guard = admin_guard()
    if guard:
        return guard
    db = get_db()
    db.execute('DELETE FROM products WHERE id = ?', (product_id,))
    db.commit()
    flash('Produsul a fost șters.', 'info')
    return redirect(url_for('admin_products'))


@app.route('/admin/orders')
def admin_orders():
    guard = admin_guard()
    if guard:
        return guard
    orders = get_db().execute('SELECT * FROM orders ORDER BY id DESC').fetchall()
    return render_template('admin/orders.html', orders=orders, payment_label=payment_label)


@app.route('/admin/orders/<int:order_id>/mark-return', methods=['POST'])
def admin_mark_order_return(order_id: int):
    guard = admin_guard()
    if guard:
        return guard

    db = get_db()
    order = db.execute('SELECT id FROM orders WHERE id = ?', (order_id,)).fetchone()
    if not order:
        flash('Comanda nu există.', 'danger')
        return redirect(url_for('admin_orders'))

    db.execute("UPDATE orders SET status = 'Retur acceptat' WHERE id = ?", (order_id,))
    db.execute("UPDATE returns SET status = 'Retur acceptat', updated_at = CURRENT_TIMESTAMP WHERE order_id = ?", (order_id,))
    db.commit()
    flash('Comanda a fost marcată ca retur acceptat.', 'success')
    return redirect(url_for('admin_orders'))


@app.route('/admin/orders/<int:order_id>/delete', methods=['POST'])
def admin_delete_order(order_id: int):
    guard = admin_guard()
    if guard:
        return guard

    db = get_db()
    order = db.execute('SELECT id FROM orders WHERE id = ?', (order_id,)).fetchone()
    if not order:
        flash('Comanda nu există.', 'danger')
        return redirect(url_for('admin_orders'))

    db.execute('DELETE FROM returns WHERE order_id = ?', (order_id,))
    db.execute('DELETE FROM invoices WHERE order_id = ?', (order_id,))
    db.execute('DELETE FROM shipments WHERE order_id = ?', (order_id,))
    db.execute('DELETE FROM order_items WHERE order_id = ?', (order_id,))
    db.execute('DELETE FROM orders WHERE id = ?', (order_id,))
    db.commit()

    flash('Comanda a fost ștearsă.', 'success')
    return redirect(url_for('admin_orders'))


@app.route('/admin/orders/<int:order_id>')
def admin_order_detail(order_id: int):
    guard = admin_guard()
    if guard:
        return guard
    db = get_db()
    order = db.execute('SELECT * FROM orders WHERE id = ?', (order_id,)).fetchone()
    if not order:
        flash('Comanda nu există.', 'danger')
        return redirect(url_for('admin_orders'))
    items = db.execute(
        '''
        SELECT oi.*, p.name
        FROM order_items oi
        JOIN products p ON p.id = oi.product_id
        WHERE oi.order_id = ?
        ORDER BY oi.id ASC
        ''',
        (order_id,),
    ).fetchall()
    shipment = db.execute('SELECT * FROM shipments WHERE order_id = ?', (order_id,)).fetchone()
    invoice = db.execute('SELECT * FROM invoices WHERE order_id = ?', (order_id,)).fetchone()
    return_request = db.execute('SELECT * FROM returns WHERE order_id = ?', (order_id,)).fetchone()
    return render_template(
        'admin/order_detail.html',
        order=order,
        items=items,
        shipment=shipment,
        invoice=invoice,
        return_request=return_request,
        payment_label=payment_label,
    )


@app.route('/admin/orders/<int:order_id>/status', methods=['POST'])
def admin_update_order_status(order_id: int):
    guard = admin_guard()
    if guard:
        return guard
    status = request.form.get('status', '').strip() or 'Nouă'
    db = get_db()
    db.execute('UPDATE orders SET status = ? WHERE id = ?', (status, order_id))
    db.commit()
    flash('Statusul comenzii a fost actualizat.', 'success')
    return redirect(url_for('admin_order_detail', order_id=order_id))


@app.route('/admin/orders/<int:order_id>/generate-awb', methods=['POST'])
def admin_generate_awb(order_id: int):
    guard = admin_guard()
    if guard:
        return guard
    courier = request.form.get('courier', 'fan')
    db = get_db()
    order = db.execute('SELECT id FROM orders WHERE id = ?', (order_id,)).fetchone()
    if not order:
        flash('Comanda nu există.', 'danger')
        return redirect(url_for('admin_orders'))
    existing = db.execute('SELECT id FROM shipments WHERE order_id = ?', (order_id,)).fetchone()
    if existing:
        flash('Există deja AWB pentru această comandă.', 'warning')
        return redirect(url_for('admin_order_detail', order_id=order_id))
    awb, tracking_url = generate_awb(courier, order_id)
    label = 'Sameday' if courier == 'sameday' else 'Fan Courier'
    db.execute(
        'INSERT INTO shipments (order_id, courier, awb, tracking_url) VALUES (?, ?, ?, ?)',
        (order_id, label, awb, tracking_url),
    )
    db.execute("UPDATE orders SET status = 'Expediată' WHERE id = ?", (order_id,))
    db.commit()
    flash('AWB-ul a fost generat automat.', 'success')
    return redirect(url_for('admin_order_detail', order_id=order_id))


@app.route('/admin/orders/<int:order_id>/generate-invoice', methods=['POST'])
def admin_generate_invoice(order_id: int):
    guard = admin_guard()
    if guard:
        return guard
    db = get_db()
    order = db.execute('SELECT * FROM orders WHERE id = ?', (order_id,)).fetchone()
    if not order:
        flash('Comanda nu există.', 'danger')
        return redirect(url_for('admin_orders'))
    existing = db.execute('SELECT id FROM invoices WHERE order_id = ?', (order_id,)).fetchone()
    if existing:
        flash('Factura există deja.', 'warning')
        return redirect(url_for('admin_order_detail', order_id=order_id))
    db.execute(
        'INSERT INTO invoices (order_id, invoice_number, total, created_by) VALUES (?, ?, ?, ?)',
        (order_id, next_invoice_number(db), float(order['total']), 'admin'),
    )
    db.commit()
    flash('Factura a fost generată.', 'success')
    return redirect(url_for('admin_order_detail', order_id=order_id))


@app.route('/admin/orders/<int:order_id>/return-status', methods=['POST'])
def admin_update_return_status(order_id: int):
    guard = admin_guard()
    if guard:
        return guard
    status = request.form.get('return_status', 'Cerere trimisă').strip()
    note = request.form.get('admin_note', '').strip()
    db = get_db()
    db.execute(
        'UPDATE returns SET status = ?, admin_note = ?, updated_at = CURRENT_TIMESTAMP WHERE order_id = ?',
        (status, note, order_id),
    )
    if status in ['Retur acceptat', 'Retur refuzat']:
        db.execute('UPDATE orders SET status = ? WHERE id = ?', (status, order_id))
    db.commit()
    flash('Returul a fost actualizat.', 'success')
    return redirect(url_for('admin_order_detail', order_id=order_id))


@app.route('/factura/<int:order_id>')
def invoice_view(order_id: int):
    db = get_db()
    order = db.execute('SELECT * FROM orders WHERE id = ?', (order_id,)).fetchone()
    invoice = db.execute('SELECT * FROM invoices WHERE order_id = ?', (order_id,)).fetchone()
    if not order or not invoice:
        flash('Factura nu există.', 'danger')
        return redirect(url_for('index'))
    items = db.execute('''
        SELECT oi.*, p.name
        FROM order_items oi
        JOIN products p ON p.id = oi.product_id
        WHERE oi.order_id = ?
        ORDER BY oi.id ASC
    ''', (order_id,)).fetchall()
    return render_template('invoice.html', order=order, invoice=invoice, items=items, payment_label=payment_label)


@app.route('/admin/messages')
def admin_messages():
    guard = admin_guard()
    if guard:
        return guard
    messages = get_db().execute('SELECT * FROM contacts ORDER BY id DESC').fetchall()
    return render_template('admin/messages.html', messages=messages)


if __name__ == '__main__':
    init_db()
    app.run(debug=True)