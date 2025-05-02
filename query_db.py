from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

import sqlite3
from werkzeug.security import generate_password_hash

DATABASE = 'app_database.db'

def add_user(username, password):
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        # Hash the password before storing it
        hashed_password = generate_password_hash(password)

        # Insert user into the database
        cursor.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, hashed_password))
        conn.commit()
        print(f"User {username} added successfully.")
    except sqlite3.IntegrityError:
        print(f"Error: Username {username} already exists.")
    finally:
        conn.close()

def get_user(username):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Query user by username
    cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
    user = cursor.fetchone()
    conn.close()

    return user