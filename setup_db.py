import sqlite3

def update_database():
    # 1. Connect to your existing database
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    # 2. Make sure existing tables are still there
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doctor_email TEXT NOT NULL,
            patient_email TEXT NOT NULL,
            age REAL, sex REAL, cp REAL, trestbps REAL, chol REAL, fbs REAL, 
            restecg REAL, thalach REAL, exang REAL, oldpeak REAL, slope REAL, 
            ca REAL, thal REAL, ai_prediction INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 3. NEW: Create the Review Queue table for the Admin
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pending_corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id INTEGER NOT NULL,
            doctor_email TEXT NOT NULL,
            proposed_diagnosis INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 4. NEW: Automatically create a Super Admin account
    cursor.execute("SELECT * FROM users WHERE email = 'admin@hospital.com'")
    admin_exists = cursor.fetchone()
    
    if not admin_exists:
        cursor.execute('''
            INSERT INTO users (name, email, password, role) 
            VALUES ('Super Admin', 'admin@hospital.com', 'admin123', 'admin')
        ''')
        print("Super Admin account created! (Email: admin@hospital.com | Password: admin123)")

    conn.commit()
    conn.close()
    print("Success! Database updated with the Review Queue and Admin role.")

if __name__ == '__main__':
    update_database()