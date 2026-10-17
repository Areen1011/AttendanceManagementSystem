CREATE DATABASE IF NOT EXISTS attendance_system
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE attendance_system;

CREATE TABLE IF NOT EXISTS admins (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(190) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS teachers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    email VARCHAR(190) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    class VARCHAR(80) NOT NULL,
    INDEX idx_teachers_class (class)
);

CREATE TABLE IF NOT EXISTS students (
    id INT AUTO_INCREMENT PRIMARY KEY,
    roll_no INT NOT NULL,
    name VARCHAR(120) NOT NULL,
    class VARCHAR(80) NOT NULL,
    UNIQUE KEY uq_students_class_roll (class, roll_no),
    INDEX idx_students_class_name (class, name)
);

CREATE TABLE IF NOT EXISTS attendance (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    date DATE NOT NULL,
    status ENUM('Present', 'Absent') NOT NULL,
    UNIQUE KEY uq_attendance_student_date (student_id, date),
    INDEX idx_attendance_date_status (date, status),
    CONSTRAINT fk_attendance_student
        FOREIGN KEY (student_id) REFERENCES students(id)
        ON DELETE CASCADE
);

ALTER TABLE admins MODIFY COLUMN password VARCHAR(255) NOT NULL;
ALTER TABLE teachers MODIFY COLUMN password VARCHAR(255) NOT NULL;
