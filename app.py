from flask import Flask, render_template, request, jsonify, redirect, url_for
from datetime import datetime, timedelta
import json

app = Flask(__name__)

# In-memory database (for demonstration - in production, use a real database)
class Database:
    def __init__(self):
        self.rooms = self._initialize_rooms()
        self.bookings = []
        self.guests = []
        self.booking_id_counter = 1
        self.guest_id_counter = 1

    def _initialize_rooms(self):
        room_types = [
            {'type': 'Deluxe', 'base_price': 3500},
            {'type': 'Deluxe', 'base_price': 3500},
            {'type': 'Premium', 'base_price': 4500},
            {'type': 'Premium', 'base_price': 4500},
            {'type': 'Suite', 'base_price': 6000},
            {'type': 'Suite', 'base_price': 6000},
            {'type': 'Executive Suite', 'base_price': 7500},
            {'type': 'Executive Suite', 'base_price': 7500}
        ]

        rooms = []
        for i, room_info in enumerate(room_types, 1):
            rooms.append({
                'room_id': i,
                'room_number': f'10{i}',
                'room_type': room_info['type'],
                'base_price': room_info['base_price'],
                'status': 'available',  # available, occupied, maintenance
                'floor': 1 if i <= 4 else 2,
                'amenities': ['WiFi', 'AC', 'TV', 'Mini Fridge', 'Kitchenette'],
                'current_guest_id': None,  # Track who's checked in
                'current_booking_id': None  # Track active booking
            })
        return rooms

    def get_room(self, room_id):
        return next((r for r in self.rooms if r['room_id'] == room_id), None)

    def get_guest(self, guest_id):
        return next((g for g in self.guests if g['guest_id'] == guest_id), None)

    def get_booking(self, booking_id):
        return next((b for b in self.bookings if b['booking_id'] == booking_id), None)

    def get_room_with_guest_details(self, room_id):
        """Get room with current guest information"""
        room = self.get_room(room_id)
        if not room:
            return None

        room_data = room.copy()

        # Add current guest details if occupied
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
        """Get guest with all their bookings and current room"""
        guest = self.get_guest(guest_id)
        if not guest:
            return None

        guest_data = guest.copy()

        # Get all bookings for this guest
        guest_bookings = [b for b in self.bookings if b['guest_id'] == guest_id]

        # Find current/active booking
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
        room = self.get_room(room_id)
        if room:
            room['status'] = status
            room['current_guest_id'] = guest_id
            room['current_booking_id'] = booking_id
            return room
        return None

    def update_room_price(self, room_id, new_price):
        room = self.get_room(room_id)
        if room:
            room['base_price'] = new_price
            return room
        return None

    def get_available_rooms(self, check_in, check_out):
        available = []
        for room in self.rooms:
            if room['status'] != 'maintenance' and self._is_room_available(room['room_id'], check_in, check_out):
                available.append(room)
        return available

    def _is_room_available(self, room_id, check_in, check_out):
        check_in_dt = datetime.strptime(check_in, '%Y-%m-%d')
        check_out_dt = datetime.strptime(check_out, '%Y-%m-%d')

        for booking in self.bookings:
            if booking['room_id'] == room_id and booking['status'] in ['confirmed', 'checked_in']:
                booking_in = datetime.strptime(booking['check_in'], '%Y-%m-%d')
                booking_out = datetime.strptime(booking['check_out'], '%Y-%m-%d')

                if (check_in_dt < booking_out and check_out_dt > booking_in):
                    return False
        return True

    def create_booking(self, booking_data):
        booking = {
            'booking_id': self.booking_id_counter,
            'room_id': booking_data['room_id'],
            'guest_id': booking_data['guest_id'],
            'check_in': booking_data['check_in'],
            'check_out': booking_data['check_out'],
            'total_price': booking_data['total_price'],
            'status': 'confirmed',
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'checked_in_at': None,
            'checked_out_at': None
        }
        self.bookings.append(booking)
        self.booking_id_counter += 1

        # Update room - mark as occupied and assign guest
        self.update_room_status(
            booking_data['room_id'], 
            'occupied',
            guest_id=booking_data['guest_id'],
            booking_id=booking['booking_id']
        )

        return booking

    def update_booking_status(self, booking_id, new_status):
        booking = self.get_booking(booking_id)
        if booking:
            old_status = booking['status']
            booking['status'] = new_status

            # Track timestamps
            if new_status == 'checked_in':
                booking['checked_in_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                self.update_room_status(
                    booking['room_id'], 
                    'occupied',
                    guest_id=booking['guest_id'],
                    booking_id=booking_id
                )
            elif new_status == 'checked_out':
                booking['checked_out_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                # Check if there are other active bookings for this room
                other_active = any(
                    b['room_id'] == booking['room_id'] and 
                    b['booking_id'] != booking_id and 
                    b['status'] in ['confirmed', 'checked_in']
                    for b in self.bookings
                )
                if not other_active:
                    self.update_room_status(booking['room_id'], 'available')
            elif new_status == 'cancelled':
                other_active = any(
                    b['room_id'] == booking['room_id'] and 
                    b['booking_id'] != booking_id and 
                    b['status'] in ['confirmed', 'checked_in']
                    for b in self.bookings
                )
                if not other_active:
                    self.update_room_status(booking['room_id'], 'available')

            return booking
        return None

    def create_guest(self, guest_data):
        guest = {
            'guest_id': self.guest_id_counter,
            'name': guest_data['name'],
            'email': guest_data['email'],
            'phone': guest_data['phone'],
            'id_proof': guest_data.get('id_proof', ''),
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        self.guests.append(guest)
        self.guest_id_counter += 1
        return guest

    def get_checked_in_guests(self):
        """Get all currently checked-in guests with room details"""
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

# ============== WEB ROUTES ==============

@app.route('/')
def index():
    return render_template('index.html', hotel=HOTEL_INFO)

@app.route('/dashboard')
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

        if new_status in ['available', 'occupied', 'maintenance']:
            room['status'] = new_status

        try:
            if new_price:
                room['base_price'] = int(new_price)
        except:
            pass

        return redirect(url_for('rooms'))

    return render_template('edit_room.html', room=room, hotel=HOTEL_INFO)

@app.route('/bookings')
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
        guest_data = {
            'name': request.form['guest_name'],
            'email': request.form['guest_email'],
            'phone': request.form['guest_phone'],
            'id_proof': request.form.get('id_proof', '')
        }
        guest = db.create_guest(guest_data)

        check_in = datetime.strptime(request.form['check_in'], '%Y-%m-%d')
        check_out = datetime.strptime(request.form['check_out'], '%Y-%m-%d')
        nights = (check_out - check_in).days

        room_id = int(request.form['room_id'])
        room = db.get_room(room_id)
        total_price = room['base_price'] * nights

        booking_data = {
            'room_id': room_id,
            'guest_id': guest['guest_id'],
            'check_in': request.form['check_in'],
            'check_out': request.form['check_out'],
            'total_price': total_price
        }
        booking = db.create_booking(booking_data)

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
def api_checked_in_guests():
    """Get all currently checked-in guests with room details"""
    checked_in = db.get_checked_in_guests()

    return jsonify({
        'success': True,
        'data': checked_in
    })

@app.route('/api/occupancy', methods=['GET'])
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
    app.run(debug=True, host='0.0.0.0', port=5000)
