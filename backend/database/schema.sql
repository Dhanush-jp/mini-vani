CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    role ENUM('ADMIN', 'TEACHER', 'STUDENT') NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE teachers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL UNIQUE,
    department VARCHAR(120) NOT NULL,
    CONSTRAINT fk_teachers_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE students (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL UNIQUE,
    roll_number VARCHAR(32) NOT NULL UNIQUE,
    department VARCHAR(120) NOT NULL,
    year INT NOT NULL,
    section VARCHAR(20) NOT NULL,
<<<<<<< HEAD
    cgpa FLOAT NOT NULL DEFAULT 0.0,
    sgpa FLOAT NOT NULL DEFAULT 0.0,
=======
>>>>>>> ea6b7ff31a97e9ad4b4c4ec3310d6e06de6a5479
    CONSTRAINT fk_students_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE teacher_students (
    id INT AUTO_INCREMENT PRIMARY KEY,
    teacher_id INT NOT NULL,
    student_id INT NOT NULL,
    CONSTRAINT uq_teacher_student UNIQUE (teacher_id, student_id),
    CONSTRAINT fk_teacher_students_teacher FOREIGN KEY (teacher_id) REFERENCES teachers(id) ON DELETE CASCADE,
    CONSTRAINT fk_teacher_students_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
);

CREATE TABLE subjects (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    code VARCHAR(24) NOT NULL UNIQUE,
    semester INT NOT NULL
);

CREATE TABLE student_subjects (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    subject_id INT NOT NULL,
    CONSTRAINT uq_student_subject UNIQUE (student_id, subject_id),
    CONSTRAINT fk_student_subjects_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    CONSTRAINT fk_student_subjects_subject FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE
);

CREATE TABLE grades (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    subject_id INT NOT NULL,
    marks DECIMAL(5, 2) NOT NULL,
    grade VARCHAR(4) NOT NULL,
    is_pass BOOLEAN NOT NULL,
    semester INT NOT NULL,
    CONSTRAINT uq_grade_scope UNIQUE (student_id, subject_id, semester),
    CONSTRAINT fk_grades_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    CONSTRAINT fk_grades_subject FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE
);

CREATE TABLE attendance (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    subject_id INT NOT NULL,
    date DATE NOT NULL,
    status ENUM('PRESENT', 'ABSENT', 'LEAVE') NOT NULL,
    CONSTRAINT uq_attendance_scope UNIQUE (student_id, subject_id, date),
    CONSTRAINT fk_attendance_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    CONSTRAINT fk_attendance_subject FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE
);

CREATE TABLE semester_results (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    semester INT NOT NULL,
    sgpa FLOAT NOT NULL,
    cgpa FLOAT NOT NULL,
    backlogs INT NOT NULL DEFAULT 0,
    CONSTRAINT uq_semester_result_scope UNIQUE (student_id, semester),
    CONSTRAINT fk_semester_results_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
);

CREATE TABLE risk_analysis (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL UNIQUE,
    risk_score FLOAT NOT NULL,
    prediction_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    suggestions VARCHAR(1024) NOT NULL,
    CONSTRAINT fk_risk_analysis_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
);

CREATE TABLE exports (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    type ENUM('STUDENTS', 'SINGLE_STUDENT') NOT NULL,
    filters JSON NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_exports_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
