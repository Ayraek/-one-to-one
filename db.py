# db.py
import sqlite3
import logging

def init_db():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            name TEXT,
            age INTEGER,
            level TEXT DEFAULT 'Junior',
            points REAL DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()
    logging.info("Database initialized")

# ... остальные функции (add_user_to_db, get_user_data)
import sqlite3
import logging

def init_db():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            name TEXT,
            age INTEGER,
            level TEXT DEFAULT 'Junior',
            points REAL DEFAULT 0,
            daily_tasks INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

def add_user_to_db(user_id, username, name, age):
    try:
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (id, username, name, age) 
            VALUES (?, ?, ?, ?)
        ''', (user_id, username, name, age))
        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"DB error: {e}")
    finally:
        conn.close()

def get_user_data(user_id):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    user_data = cursor.fetchone()
    conn.close()
    return user_data