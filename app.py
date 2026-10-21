from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from datetime import datetime, timedelta
from functools import wraps
import json
import os
import mysql.connector

try:
    # local, git-ignored credentials (see db_config.example.py)
    from db_config import DB_PASSWORD as _LOCAL_DB_PASSWORD
except ImportError:
    _LOCAL_DB_PASSWORD = ''

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dummy-pms-dev-secret-key-change-me')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=20)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

if os.environ.get('FLASK_ENV') != 'development':
    app.config['SESSION_COOKIE_SECURE'] = True

# MySQL-backed Database
class Database:
    def __init__(self):
        self.config = {
            'host': os.environ.get('DB_HOST', 'localhost'),
            'user': os.environ.get('DB_USER', 'root'),
            'password': os.environ.get('DB_PASSWORD', _LOCAL_DB_PASSWORD),
            'database': os.environ.get('DB_NAME', 'dummy_pms')
        }

    def _get_connection(self):
        return mysql.connector.connect(**self.config)

    @property
    def rooms(self):
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM rooms")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        for r in rows:
            if isinstance(r.get('base_price'), (int, float, str)):
                r['base_price'] = float(r['base_price'])
            if isinstance(r.get('amenities'), str):
                r['amenities'] = [a.strip() for a in r['amenities'].split(',') if a.strip()]
        return rows

    @property
    def bookings(self):
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM bookings")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        for b in rows:
            if b.get('check_in'):
                b['check_in'] = str(b['check_in'])
            if b.get('check_out'):
                b['check_out'] = str(b['check_out'])
            if b.get('created_at'):
                b['created_at'] = str(b['created_at'])
            if b.get('checked_in_at'):
                b['checked_in_at'] = str(b['checked_in_at'])
            if b.get('checked_out_at'):
                b['checked_out_at'] = str(b['checked_out_at'])
            if b.get('total_price') is not None:
                b['total_price'] = float(b['total_price'])
        return rows

    @property
    def guests(self):
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM guests")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        for g in rows:
            if g.get('created_at'):
                g['created_at'] = str(g['created_at'])
        return rows

    def get_room(self, room_id):
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM rooms WHERE room_id = %s", (room_id,))
        room = cursor.fetchone()
        cursor.close()
        conn.close()
        if room:
            room['base_price'] = float(room['base_price'])
            if isinstance(room.get('amenities'), str):
                room['amenities'] = [a.strip() for a in room['amenities'].split(',') if a.strip()]
        return room

    def get_guest(self, guest_id):
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM guests WHERE guest_id = %s", (guest_id,))
        guest = cursor.fetchone()
        cursor.close()
        conn.close()
        if guest and guest.get('created_at'):
            guest['created_at'] = str(guest['created_at'])
        return guest

    def get_booking(self, booking_id):
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM bookings WHERE booking_id = %s", (booking_id,))
        booking = cursor.fetchone()
        cursor.close()
        conn.close()
        if booking:
            if booking.get('check_in'):
                booking['check_in'] = str(booking['check_in'])
            if booking.get('check_out'):
                booking['check_out'] = str(booking['check_out'])
            if booking.get('created_at'):
                booking['created_at'] = str(booking['created_at'])
            if booking.get('checked_in_at'):
                booking['checked_in_at'] = str(booking['checked_in_at'])
            if booking.get('checked_out_at'):
                booking['checked_out_at'] = str(booking['checked_out_at'])
            if booking.get('total_price') is not None:
                booking['total_price'] = float(booking['total_price'])
        return booking

    def get_room_with_guest_details(self, room_id):
        room = self.get_room(room_id)
        if not room:
            return None

        room_data = room.copy()
        if room['current_guest_id']:
            guest = self.get_guest(room['current_guest_id'])
            booking = self.get_booking(room['current_booking_id'])
            room_data['current_guest'] = {
                'guest_id': guest['guest_id'],
                'name': guest['name'],
                'email': guest['email'],
                'phone': guest['phone'],
                'check_in': booking['check_in'] if booking else None,
                'check_out': booking['check_out'] if booking else None,
                'booking_id': booking['booking_id'] if booking else None
            } if guest else None
        else:
            room_data['current_guest'] = None

        return room_data

    def get_guest_with_booking_details(self, guest_id):
        guest = self.get_guest(guest_id)
        if not guest:
            return None

        guest_data = guest.copy()
        guest_bookings = [b for b in self.bookings if b['guest_id'] == guest_id]

        current_booking = next(
            (b for b in guest_bookings if b['status'] in ['confirmed', 'checked_in']),
            None
        )

        enriched_bookings = []
        for booking in guest_bookings:
            room = self.get_room(booking['room_id'])
            enriched_bookings.append({
                **booking,
                'room_number': room['room_number'] if room else None,
                'room_type': room['room_type'] if room else None
            })

        guest_data['bookings'] = enriched_bookings
        guest_data['current_booking'] = None
        guest_data['current_room'] = None

        if current_booking:
            room = self.get_room(current_booking['room_id'])
            guest_data['current_booking'] = current_booking
            guest_data['current_room'] = {
                'room_id': room['room_id'],
                'room_number': room['room_number'],
                'room_type': room['room_type']
            } if room else None

        return guest_data

    def update_room_status(self, room_id, status, guest_id=None, booking_id=None):
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE rooms SET status = %s, current_guest_id = %s, current_booking_id = %s WHERE room_id = %s",
            (status, guest_id, booking_id, room_id)
        )
        conn.commit()
        cursor.close()
        conn.close()
        return self.get_room(room_id)

    def update_room_price(self, room_id, new_price):
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE rooms SET base_price = %s WHERE room_id = %s", (new_price, room_id))
        conn.commit()
        cursor.close()
        conn.close()
        return self.get_room(room_id)

    def get_available_rooms(self, check_in, check_out):
        available = []
        for room in self.rooms:
            if room['status'] != 'maintenance' and self._is_room_available(room['room_id'], check_in, check_out):
                available.append(room)
        return available

    def _is_room_available(self, room_id, check_in, check_out):
        check_in_dt = datetime.strptime(str(check_in), '%Y-%m-%d')
        check_out_dt = datetime.strptime(str(check_out), '%Y-%m-%d')
        for booking in self.bookings:
            if booking['room_id'] == room_id and booking['status'] in ['confirmed', 'checked_in']:
                booking_in = datetime.strptime(str(booking['check_in']), '%Y-%m-%d')
                booking_out = datetime.strptime(str(booking['check_out']), '%Y-%m-%d')
                if (check_in_dt < booking_out and check_out_dt > booking_in):
                    return False
        return True

    def create_booking(self, booking_data):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute(
                """INSERT INTO bookings (room_id, guest_id, check_in, check_out, total_price, status, created_at)
                   VALUES (%s, %s, %s, %s, %s, 'confirmed', %s)""",
                (booking_data['room_id'], booking_data['guest_id'], booking_data['check_in'],
                 booking_data['check_out'], booking_data['total_price'], now_str)
            )
            booking_id = cursor.lastrowid
            conn.commit()
        finally:
            cursor.close()
            conn.close()

        self.update_room_status(
            booking_data['room_id'],
            'occupied',
            guest_id=booking_data['guest_id'],
            booking_id=booking_id
        )
        return self.get_booking(booking_id)

    def update_booking_status(self, booking_id, new_status):
        booking = self.get_booking(booking_id)
        if not booking:
            return None

        conn = self._get_connection()
        cursor = conn.cursor()
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if new_status == 'checked_in':
            cursor.execute(
                "UPDATE bookings SET status = %s, checked_in_at = %s WHERE booking_id = %s",
                (new_status, now_str, booking_id)
            )
            conn.commit()
            cursor.close()
            conn.close()
            self.update_room_status(
                booking['room_id'],
                'occupied',
                guest_id=booking['guest_id'],
                booking_id=booking_id
            )
        elif new_status in ['checked_out', 'cancelled']:
            cursor.execute(
                "UPDATE bookings SET status = %s, checked_out_at = %s WHERE booking_id = %s",
                (new_status, now_str, booking_id)
            )
            conn.commit()
            cursor.close()
            conn.close()

            all_bookings = self.bookings
            other_active = any(
                b['room_id'] == booking['room_id'] and
                b['booking_id'] != booking_id and
                b['status'] in ['confirmed', 'checked_in']
                for b in all_bookings
            )
            if not other_active:
                self.update_room_status(booking['room_id'], 'available')
        else:
            cursor.execute("UPDATE bookings SET status = %s WHERE booking_id = %s", (new_status, booking_id))
            conn.commit()
            cursor.close()
            conn.close()

        return self.get_booking(booking_id)

    def create_guest(self, guest_data):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute(
                """INSERT INTO guests (name, email, phone, id_proof, created_at)
                   VALUES (%s, %s, %s, %s, %s)""",
                (guest_data['name'], guest_data['email'], guest_data['phone'],
                 guest_data.get('id_proof', ''), now_str)
            )
            guest_id = cursor.lastrowid
            conn.commit()
        finally:
            # always release the connection, even if the INSERT failed,
            # otherwise the open transaction keeps locks held
            cursor.close()
            conn.close()
        return self.get_guest(guest_id)

    def get_checked_in_guests(self):
        checked_in = []
        for booking in self.bookings:
            if booking['status'] == 'checked_in':
                guest = self.get_guest(booking['guest_id'])
                room = self.get_room(booking['room_id'])
                if guest and room:
                    checked_in.append({
                        'guest_id': guest['guest_id'],
                        'guest_name': guest['name'],
                        'guest_email': guest['email'],
                        'guest_phone': guest['phone'],
                        'room_id': room['room_id'],
                        'room_number': room['room_number'],
                        'room_type': room['room_type'],
                        'booking_id': booking['booking_id'],
                        'check_in': booking['check_in'],
                        'check_out': booking['check_out'],
                        'checked_in_at': booking.get('checked_in_at')
                    })
        return checked_in


USERS = {
    'manager': {
        'password': 'manager123',
        'role': 'manager',
        'name': 'Hotel Manager'
    },
    'reception': {
        'password': 'reception123',
        'role': 'reception',
        'name': 'Front Desk Receptionist'
    },
    'auditor': {
        'password': 'auditor123',
        'role': 'auditor',
        'name': 'Security Auditor'
    }
}

FAILED_LOGIN_TRACKER = {}
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 2


def _get_client_ip():
    forwarded_for = request.headers.get('X-Forwarded-For', '')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.remote_addr or 'unknown'


def _is_login_locked(username, client_ip):
    key = f'{username}:{client_ip}'
    record = FAILED_LOGIN_TRACKER.get(key)

    if not record:
        return False, 0

    lock_until = record.get('lock_until')
    if lock_until and datetime.now() < lock_until:
        remaining_seconds = int((lock_until - datetime.now()).total_seconds())
        return True, max(remaining_seconds, 1)

    if lock_until and datetime.now() >= lock_until:
        FAILED_LOGIN_TRACKER.pop(key, None)

    return False, 0


def _record_failed_login(username, client_ip):
    key = f'{username}:{client_ip}'
    record = FAILED_LOGIN_TRACKER.get(key, {'count': 0, 'lock_until': None})
    record['count'] += 1

    if record['count'] >= MAX_FAILED_ATTEMPTS:
        record['lock_until'] = datetime.now() + timedelta(minutes=LOCKOUT_MINUTES)

    FAILED_LOGIN_TRACKER[key] = record
    return record


def _clear_failed_logins(username, client_ip):
    key = f'{username}:{client_ip}'
    FAILED_LOGIN_TRACKER.pop(key, None)


def get_current_user():
    username = session.get('username')
    role = session.get('role')
    name = session.get('display_name')

    if username and role:
        return {
            'username': username,
            'role': role,
            'name': name or username
        }

    return None


@app.context_processor
def inject_template_globals():
    return {
        'current_user': get_current_user()
    }


def login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not get_current_user():
            if request.path.startswith('/api/'):
                return jsonify({'success': False, 'error': 'Authentication required'}), 401
            return redirect(url_for('login', next=request.path))
        return view_func(*args, **kwargs)
    return wrapped_view


def roles_required(*allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(*args, **kwargs):
            user = get_current_user()
            if not user:
                if request.path.startswith('/api/'):
                    return jsonify({'success': False, 'error': 'Authentication required'}), 401
                return redirect(url_for('login', next=request.path))

            if user['role'] not in allowed_roles:
                if request.path.startswith('/api/'):
                    return jsonify({'success': False, 'error': 'Forbidden: insufficient role'}), 403
                flash('You do not have permission to access that page.', 'error')
                return redirect(url_for('dashboard'))

            return view_func(*args, **kwargs)
        return wrapped_view
    return decorator


@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'"
    return response

# Initialize database
db = Database()

# Hotel Information
HOTEL_INFO = {
    'name': 'Chennai BnB Serviced Apartments',
    'location': 'Chennai, Tamil Nadu, India',
    'address': 'Thiru Nagar, Chennai',
    'total_rooms': 8,
    'contact': '+91-XXXXXXXXXX',
    'email': 'info@chennaibnb.com',
    'amenities': ['Free WiFi', '24/7 Reception', 'Housekeeping', 'Kitchen Facilities', 'Parking'],
    'check_in_time': '14:00',
    'check_out_time': '11:00'
}


@app.route('/login', methods=['GET', 'POST'])
def login():
    if get_current_user():
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = (request.form.get('username') or '').strip().lower()
        password = request.form.get('password') or ''

        user = USERS.get(username)
        if not user or user['password'] != password:
            flash('Invalid credentials.', 'error')
            return render_template('login.html', hotel=HOTEL_INFO, username=username), 401

        session.clear()
        session.permanent = True
        session['username'] = username
        session['role'] = user['role']
        session['display_name'] = user['name']

        next_path = request.args.get('next')
        if next_path and next_path.startswith('/'):
            return redirect(next_path)
        return redirect(url_for('dashboard'))

    return render_template('login.html', hotel=HOTEL_INFO)


@app.route('/logout', methods=['GET'])
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


@app.route('/')
def index():
    return render_template('index.html', hotel=HOTEL_INFO)


@app.route('/dashboard')
@login_required
def dashboard():
    today = datetime.now().date()

    occupied_rooms = len([r for r in db.rooms if r['status'] == 'occupied'])
    available_rooms = len([r for r in db.rooms if r['status'] == 'available'])
    maintenance_rooms = len([r for r in db.rooms if r['status'] == 'maintenance'])
    occupancy_rate = (occupied_rooms / 8) * 100

    today_str = today.strftime('%Y-%m-%d')
    check_ins_today = [b for b in db.bookings if b['check_in'] == today_str and b['status'] == 'confirmed']
    check_outs_today = [b for b in db.bookings if b['check_out'] == today_str and b['status'] == 'checked_in']

    # Get checked-in guests
    checked_in_guests = db.get_checked_in_guests()

    return render_template('dashboard.html', 
                         occupancy_rate=occupancy_rate,
                         total_rooms=8,
                         occupied_rooms=occupied_rooms,
                         available_rooms=available_rooms,
                         maintenance_rooms=maintenance_rooms,
                         check_ins=len(check_ins_today),
                         check_outs=len(check_outs_today),
                         checked_in_guests=checked_in_guests,
                         hotel=HOTEL_INFO)

@app.route('/rooms')
@login_required
def rooms():
    # Get rooms with guest details
    rooms_with_guests = []
    for room in db.rooms:
        room_data = db.get_room_with_guest_details(room['room_id'])
        rooms_with_guests.append(room_data)

    return render_template('rooms.html', rooms=rooms_with_guests, hotel=HOTEL_INFO)

@app.route('/rooms/edit/<int:room_id>', methods=['GET', 'POST'])
def edit_room(room_id):
    room = db.get_room(room_id)
    if not room:
        return "Room not found", 404

    if request.method == 'POST':
        new_status = request.form.get('status')
        new_price = request.form.get('base_price')

        # Validate and persist the price to the database
        if new_price not in (None, ''):
            try:
                price_val = float(new_price)
            except (TypeError, ValueError):
                flash('Invalid price format.', 'error')
                return render_template('edit_room.html', room=room, hotel=HOTEL_INFO), 400
            if price_val <= 0:
                flash('Price must be greater than 0.', 'error')
                return render_template('edit_room.html', room=room, hotel=HOTEL_INFO), 400
            db.update_room_price(room_id, price_val)

        # Validate and persist the status, preserving current occupant linkage
        if new_status in ['available', 'occupied', 'maintenance']:
            db.update_room_status(
                room_id,
                new_status,
                guest_id=room.get('current_guest_id'),
                booking_id=room.get('current_booking_id')
            )

        return redirect(url_for('rooms'))

    return render_template('edit_room.html', room=room, hotel=HOTEL_INFO)

@app.route('/bookings')
@login_required
def bookings():
    enriched_bookings = []
    for booking in db.bookings:
        room = db.get_room(booking['room_id'])
        guest = db.get_guest(booking['guest_id'])
        enriched_bookings.append({
            **booking,
            'room_number': room['room_number'] if room else 'N/A',
            'room_type': room['room_type'] if room else 'N/A',
            'guest_name': guest['name'] if guest else 'N/A'
        })

    return render_template('bookings.html', bookings=enriched_bookings, hotel=HOTEL_INFO)

@app.route('/bookings/update-status/<int:booking_id>/<status>')
def update_booking_status_route(booking_id, status):
    if status in ['confirmed', 'checked_in', 'checked_out', 'cancelled']:
        db.update_booking_status(booking_id, status)
    return redirect(url_for('bookings'))

@app.route('/new-booking', methods=['GET', 'POST'])
def new_booking():
    if request.method == 'POST':
        def _reject(message):
            flash(message, 'error')
            available_rooms = [r for r in db.rooms if r['status'] == 'available']
            return render_template('new_booking.html', rooms=available_rooms, hotel=HOTEL_INFO), 400

        # Validate required fields are present and non-empty
        required = ['guest_name', 'guest_email', 'guest_phone', 'room_id', 'check_in', 'check_out']
        if any(not (request.form.get(f) or '').strip() for f in required):
            return _reject('All fields are required.')

        # Validate date format
        try:
            check_in = datetime.strptime(request.form['check_in'], '%Y-%m-%d')
            check_out = datetime.strptime(request.form['check_out'], '%Y-%m-%d')
        except ValueError:
            return _reject('Invalid date format.')

        # Validate date ordering
        nights = (check_out - check_in).days
        if nights <= 0:
            return _reject('Check-out must be after check-in.')

        # Validate room exists and is available for the dates
        try:
            room_id = int(request.form['room_id'])
        except ValueError:
            return _reject('Invalid room selection.')
        room = db.get_room(room_id)
        if not room:
            return _reject('Selected room does not exist.')
        if not db._is_room_available(room_id, request.form['check_in'], request.form['check_out']):
            return _reject('Room is not available for the selected dates.')

        # All valid — create the guest and booking
        guest = db.create_guest({
            'name': request.form['guest_name'],
            'email': request.form['guest_email'],
            'phone': request.form['guest_phone'],
            'id_proof': request.form.get('id_proof', '')
        })
        db.create_booking({
            'room_id': room_id,
            'guest_id': guest['guest_id'],
            'check_in': request.form['check_in'],
            'check_out': request.form['check_out'],
            'total_price': room['base_price'] * nights
        })

        return redirect(url_for('bookings'))

    available_rooms = [r for r in db.rooms if r['status'] == 'available']
    return render_template('new_booking.html', rooms=available_rooms, hotel=HOTEL_INFO)

@app.route('/guests')
def guests_page():
    # Get all guests with their booking details
    guests_with_details = []
    for guest in db.guests:
        guest_data = db.get_guest_with_booking_details(guest['guest_id'])
        guests_with_details.append(guest_data)

    return render_template('guests.html', guests=guests_with_details, hotel=HOTEL_INFO)

# ============== API ENDPOINTS ==============

@app.route('/api/hotel-info', methods=['GET'])
def api_hotel_info():
    """Get complete hotel information"""
    return jsonify({
        'success': True,
        'data': HOTEL_INFO
    })

@app.route('/api/rooms', methods=['GET'])
def api_rooms():
    """Get all rooms with current guest information"""
    rooms_with_guests = []
    for room in db.rooms:
        room_data = db.get_room_with_guest_details(room['room_id'])
        rooms_with_guests.append(room_data)

    return jsonify({
        'success': True,
        'data': rooms_with_guests
    })

@app.route('/api/rooms/<int:room_id>', methods=['GET', 'PUT'])
def api_room_detail(room_id):

    """Get or update specific room details with guest information"""
    room = db.get_room_with_guest_details(room_id)

    if not room:
        return jsonify({
            'success': False,
            'error': 'Room not found'
        }), 404

    if request.method == 'GET':
        return jsonify({
            'success': True,
            'data': room
        })

    if request.method == 'PUT':
        data = request.get_json()
        room_basic = db.get_room(room_id)

        if 'status' in data:
            if data['status'] not in ['available', 'occupied', 'maintenance']:
                return jsonify({
                    'success': False,
                    'error': 'Invalid status'
                }), 400
            room_basic['status'] = data['status']

        if 'base_price' in data:
            try:
                new_price = float(data['base_price'])
                if new_price <= 0:
                    return jsonify({
                        'success': False,
                        'error': 'Price must be greater than 0'
                    }), 400
                room_basic['base_price'] = new_price
            except ValueError:
                return jsonify({
                    'success': False,
                    'error': 'Invalid price format'
                }), 400

        updated_room = db.get_room_with_guest_details(room_id)
        return jsonify({
            'success': True,
            'data': updated_room,
            'message': 'Room updated successfully'
        })

@app.route('/api/rooms/<int:room_id>/guest', methods=['GET'])
@roles_required('manager', 'reception', 'auditor')
def api_room_current_guest(room_id):
    """Get current guest checked into a specific room"""
    room = db.get_room_with_guest_details(room_id)

    if not room:
        return jsonify({
            'success': False,
            'error': 'Room not found'
        }), 404

    if room['current_guest']:
        return jsonify({
            'success': True,
            'data': room['current_guest']
        })
    else:
        return jsonify({
            'success': True,
            'data': None,
            'message': 'No guest currently checked in'
        })

@app.route('/api/rooms/available', methods=['GET'])
@roles_required('manager', 'reception', 'auditor')
def api_available_rooms():
    """Get available rooms for specific dates"""
    check_in = request.args.get('check_in')
    check_out = request.args.get('check_out')

    if not check_in or not check_out:
        return jsonify({
            'success': False,
            'error': 'check_in and check_out dates are required'
        }), 400

    try:
        available = db.get_available_rooms(check_in, check_out)
        return jsonify({
            'success': True,
            'data': available
        })
    except ValueError:
        return jsonify({
            'success': False,
            'error': 'Invalid date format'
        }), 400

@app.route('/api/bookings', methods=['GET', 'POST'])
def api_bookings():

    """Get all bookings or create a new booking"""
    if request.method == 'GET':
        enriched_bookings = []
        for booking in db.bookings:
            room = db.get_room(booking['room_id'])
            guest = db.get_guest(booking['guest_id'])
            enriched_bookings.append({
                **booking,
                'room_number': room['room_number'] if room else 'N/A',
                'room_type': room['room_type'] if room else 'N/A',
                'guest_name': guest['name'] if guest else 'N/A',
                'guest_email': guest['email'] if guest else 'N/A',
                'guest_phone': guest['phone'] if guest else 'N/A'
            })

        return jsonify({
            'success': True,
            'data': enriched_bookings
        })

    if request.method == 'POST':
        data = request.get_json()

        required = ['room_id', 'guest_name', 'guest_email', 'guest_phone', 'check_in', 'check_out']
        if not all(field in data for field in required):
            return jsonify({
                'success': False,
                'error': 'Missing required fields'
            }), 400

        room = db.get_room(data['room_id'])
        if not room:
            return jsonify({
                'success': False,
                'error': 'Room not found'
            }), 404

        if not db._is_room_available(data['room_id'], data['check_in'], data['check_out']):
            return jsonify({
                'success': False,
                'error': 'Room not available'
            }), 400

        guest_data = {
            'name': data['guest_name'],
            'email': data['guest_email'],
            'phone': data['guest_phone'],
            'id_proof': data.get('id_proof', '')
        }
        guest = db.create_guest(guest_data)

        try:
            check_in = datetime.strptime(data['check_in'], '%Y-%m-%d')
            check_out = datetime.strptime(data['check_out'], '%Y-%m-%d')
            nights = (check_out - check_in).days

            if nights <= 0:
                return jsonify({
                    'success': False,
                    'error': 'Check-out must be after check-in'
                }), 400

            total_price = room['base_price'] * nights
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'Invalid date format'
            }), 400

        booking_data = {
            'room_id': data['room_id'],
            'guest_id': guest['guest_id'],
            'check_in': data['check_in'],
            'check_out': data['check_out'],
            'total_price': total_price
        }
        booking = db.create_booking(booking_data)

        return jsonify({
            'success': True,
            'data': booking
        }), 201

@app.route('/api/bookings/<int:booking_id>', methods=['GET', 'PUT', 'DELETE'])
@roles_required('manager', 'reception')
def api_booking_detail(booking_id):
    """Get, update, or cancel booking with full details"""
    booking = db.get_booking(booking_id)

    if not booking:
        return jsonify({
            'success': False,
            'error': 'Booking not found'
        }), 404

    if request.method == 'GET':
        room = db.get_room(booking['room_id'])
        guest = db.get_guest(booking['guest_id'])

        enriched_booking = {
            **booking,
            'room_number': room['room_number'] if room else 'N/A',
            'room_type': room['room_type'] if room else 'N/A',
            'guest_name': guest['name'] if guest else 'N/A',
            'guest_email': guest['email'] if guest else 'N/A',
            'guest_phone': guest['phone'] if guest else 'N/A'
        }

        return jsonify({
            'success': True,
            'data': enriched_booking
        })

    if request.method == 'PUT':
        data = request.get_json()
        if 'status' in data:
            if data['status'] not in ['confirmed', 'checked_in', 'checked_out', 'cancelled']:
                return jsonify({
                    'success': False,
                    'error': 'Invalid status'
                }), 400

            updated_booking = db.update_booking_status(booking_id, data['status'])

            return jsonify({
                'success': True,
                'data': updated_booking
            })

        return jsonify({
            'success': False,
            'error': 'No valid fields to update'
        }), 400

    if request.method == 'DELETE':
        db.update_booking_status(booking_id, 'cancelled')
        return jsonify({
            'success': True,
            'message': 'Booking cancelled'
        })

@app.route('/api/guests', methods=['GET'])
@roles_required('manager', 'reception', 'auditor')
def api_guests():
    """Get all guests with their booking details"""
    guests_with_details = []
    for guest in db.guests:
        guest_data = db.get_guest_with_booking_details(guest['guest_id'])
        guests_with_details.append(guest_data)

    return jsonify({
        'success': True,
        'data': guests_with_details
    })

@app.route('/api/guests/<int:guest_id>', methods=['GET'])
@roles_required('manager', 'reception', 'auditor')
def api_guest_detail(guest_id):
    """Get specific guest with all bookings and current room"""
    guest_data = db.get_guest_with_booking_details(guest_id)

    if not guest_data:
        return jsonify({
            'success': False,
            'error': 'Guest not found'
        }), 404

    return jsonify({
        'success': True,
        'data': guest_data
    })

@app.route('/api/guests/checked-in', methods=['GET'])
@roles_required('manager', 'reception', 'auditor')
def api_checked_in_guests():
    """Get all currently checked-in guests with room details"""
    checked_in = db.get_checked_in_guests()

    return jsonify({
        'success': True,
        'data': checked_in
    })

@app.route('/api/occupancy', methods=['GET'])
@roles_required('manager', 'reception', 'auditor')
def api_occupancy():
    """Get current occupancy statistics"""
    occupied = len([r for r in db.rooms if r['status'] == 'occupied'])
    available = len([r for r in db.rooms if r['status'] == 'available'])
    maintenance = len([r for r in db.rooms if r['status'] == 'maintenance'])

    today = datetime.now().date().strftime('%Y-%m-%d')
    check_ins_today = len([b for b in db.bookings if b['check_in'] == today and b['status'] == 'confirmed'])
    check_outs_today = len([b for b in db.bookings if b['check_out'] == today and b['status'] == 'checked_in'])

    return jsonify({
        'success': True,
        'data': {
            'total_rooms': 8,
            'occupied_rooms': occupied,
            'available_rooms': available,
            'maintenance_rooms': maintenance,
            'occupancy_rate': (occupied / 8) * 100,
            'check_ins_today': check_ins_today,
            'check_outs_today': check_outs_today
        }
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

