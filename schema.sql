CREATE DATABASE IF NOT EXISTS dummy_pms;
USE dummy_pms;

CREATE TABLE IF NOT EXISTS rooms (
    room_id INT AUTO_INCREMENT PRIMARY KEY,
    room_number VARCHAR(10) NOT NULL UNIQUE,
    room_type VARCHAR(50) NOT NULL,
    base_price DECIMAL(10, 2) NOT NULL,
    status ENUM('available', 'occupied', 'maintenance') DEFAULT 'available',
    floor INT NOT NULL,
    amenities TEXT,
    current_guest_id INT NULL,
    current_booking_id INT NULL
);

CREATE TABLE IF NOT EXISTS guests (
    guest_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) NOT NULL,
    phone VARCHAR(20) NOT NULL,
    id_proof VARCHAR(100) DEFAULT '',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bookings (
    booking_id INT AUTO_INCREMENT PRIMARY KEY,
    room_id INT NOT NULL,
    guest_id INT NOT NULL,
    check_in DATE NOT NULL,
    check_out DATE NOT NULL,
    total_price DECIMAL(10, 2) NOT NULL,
    status ENUM('confirmed', 'checked_in', 'checked_out', 'cancelled') DEFAULT 'confirmed',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    checked_in_at DATETIME NULL,
    checked_out_at DATETIME NULL,
    FOREIGN KEY (room_id) REFERENCES rooms(room_id) ON DELETE CASCADE,
    FOREIGN KEY (guest_id) REFERENCES guests(guest_id) ON DELETE CASCADE
);

-- Seed rooms if table is empty
INSERT INTO rooms (room_id, room_number, room_type, base_price, status, floor, amenities)
SELECT 1, '101', 'Deluxe', 3500.00, 'available', 1, 'WiFi, AC, TV, Mini Fridge, Kitchenette' FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM rooms WHERE room_id = 1);

INSERT INTO rooms (room_id, room_number, room_type, base_price, status, floor, amenities)
SELECT 2, '102', 'Deluxe', 3500.00, 'available', 1, 'WiFi, AC, TV, Mini Fridge, Kitchenette' FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM rooms WHERE room_id = 2);

INSERT INTO rooms (room_id, room_number, room_type, base_price, status, floor, amenities)
SELECT 3, '103', 'Premium', 4500.00, 'available', 1, 'WiFi, AC, TV, Mini Fridge, Kitchenette' FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM rooms WHERE room_id = 3);

INSERT INTO rooms (room_id, room_number, room_type, base_price, status, floor, amenities)
SELECT 4, '104', 'Premium', 4500.00, 'available', 1, 'WiFi, AC, TV, Mini Fridge, Kitchenette' FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM rooms WHERE room_id = 4);

INSERT INTO rooms (room_id, room_number, room_type, base_price, status, floor, amenities)
SELECT 5, '105', 'Suite', 6000.00, 'available', 2, 'WiFi, AC, TV, Mini Fridge, Kitchenette' FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM rooms WHERE room_id = 5);

INSERT INTO rooms (room_id, room_number, room_type, base_price, status, floor, amenities)
SELECT 6, '106', 'Suite', 6000.00, 'available', 2, 'WiFi, AC, TV, Mini Fridge, Kitchenette' FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM rooms WHERE room_id = 6);

INSERT INTO rooms (room_id, room_number, room_type, base_price, status, floor, amenities)
SELECT 7, '107', 'Executive Suite', 7500.00, 'available', 2, 'WiFi, AC, TV, Mini Fridge, Kitchenette' FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM rooms WHERE room_id = 7);

INSERT INTO rooms (room_id, room_number, room_type, base_price, status, floor, amenities)
SELECT 8, '108', 'Executive Suite', 7500.00, 'available', 2, 'WiFi, AC, TV, Mini Fridge, Kitchenette' FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM rooms WHERE room_id = 8);
