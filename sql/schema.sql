-- MySQL 8.0.16 or later; run in the intended database.
CREATE TABLE users (
    user_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    role ENUM('Tester', 'Developer', 'Admin') NOT NULL
) ENGINE=InnoDB;

CREATE TABLE games (
    game_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    genre VARCHAR(100),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE game_versions (
    version_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    game_id INT UNSIGNED NOT NULL,
    version_name VARCHAR(100) NOT NULL,
    release_date DATE,
    UNIQUE (game_id, version_name),
    FOREIGN KEY (game_id) REFERENCES games(game_id)
) ENGINE=InnoDB;

CREATE TABLE playtest_sessions (
    session_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id INT UNSIGNED NOT NULL,
    version_id INT UNSIGNED NOT NULL,
    tested_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (session_id, version_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (version_id) REFERENCES game_versions(version_id)
) ENGINE=InnoDB;

CREATE TABLE bug_reports (
    bug_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    version_id INT UNSIGNED NOT NULL,
    title VARCHAR(255) NOT NULL,
    category VARCHAR(100) NOT NULL,
    severity TINYINT UNSIGNED NOT NULL,
    impact TINYINT UNSIGNED NOT NULL,
    status ENUM('Open', 'In Progress', 'Fixed', 'Closed') NOT NULL DEFAULT 'Open',
    CHECK (severity BETWEEN 1 AND 5),
    CHECK (impact BETWEEN 1 AND 5),
    UNIQUE (bug_id, version_id),
    FOREIGN KEY (version_id) REFERENCES game_versions(version_id)
) ENGINE=InnoDB;

CREATE TABLE bug_occurrences (
    occurrence_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    bug_id INT UNSIGNED NOT NULL,
    session_id INT UNSIGNED NOT NULL,
    version_id INT UNSIGNED NOT NULL,
    notes TEXT,
    reported_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (bug_id, version_id) REFERENCES bug_reports(bug_id, version_id),
    FOREIGN KEY (session_id, version_id) REFERENCES playtest_sessions(session_id, version_id)
) ENGINE=InnoDB;

CREATE TABLE feedback (
    feedback_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    session_id INT UNSIGNED NOT NULL UNIQUE,
    rating TINYINT UNSIGNED NOT NULL,
    comments TEXT,
    CHECK (rating BETWEEN 1 AND 5),
    FOREIGN KEY (session_id) REFERENCES playtest_sessions(session_id)
) ENGINE=InnoDB;
