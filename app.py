from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3
import joblib
import pandas as pd
import re
import base64
import io
from google import genai
from google.genai import types
from gtts import gTTS

app = Flask(__name__)
app.secret_key = 'super_secret_university_key_change_later' 

# ==========================================
# IMPORTANT: PASTE YOUR GEMINI API KEY HERE
# ==========================================
gemini_client = genai.Client(api_key="my api key")

print("Waking up the AI Brains...")
try:
    model = joblib.load("heart_disease_brain.joblib")
    scaler = joblib.load("medical_scaler.joblib")
    print("Local ML Brain loaded successfully!")
except Exception as e:
    print(f"Warning: Could not load local ML model. Error: {e}")

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row 
    return conn

# --- NEW: AUTO-CREATE ADMIN ACCOUNT ---
def init_admin():
    try:
        conn = get_db_connection()
        admin = conn.execute("SELECT * FROM users WHERE email='hosp_admin@gmail.com'").fetchone()
        if not admin:
            conn.execute("INSERT INTO users (name, email, password, role) VALUES ('Super Admin', 'hosp_admin@gmail.com', 'admin@123', 'admin')")
            conn.commit()
            print("Super Admin account generated successfully!")
        conn.close()
    except Exception as e:
        print("Database Admin Init Error:", e)

init_admin() # Runs automatically when the server starts!

# --- AUTHENTICATION ROUTES ---
@app.route('/')
def home(): return render_template('home.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name, email, password, role = request.form['name'], request.form['email'], request.form['password'], request.form['role']
        conn = get_db_connection()
        try:
            conn.execute('INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, ?)', (name, email, password, role))
            conn.commit()
            conn.close()
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            return render_template('register.html', error="Email already exists! Try logging in.")
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email, password, role = request.form['email'], request.form['password'], request.form.get('role') 
        conn = get_db_connection()
        # Removed Admin logic from here. Only Doctors and Patients use this portal.
        user = conn.execute('SELECT * FROM users WHERE email = ? AND password = ? AND role = ?', (email, password, role)).fetchone()
        conn.close()
        
        if user:
            session['user_id'], session['user_role'], session['user_email'], session['user_name'] = user['id'], user['role'], user['email'], user['name']
            if user['role'] == 'doctor': return redirect(url_for('doctor_dashboard'))
            else: return redirect(url_for('patient_dashboard'))
        else:
            return render_template('login.html', error="Invalid credentials or wrong portal.")
    return render_template('login.html')

# --- NEW: DEDICATED ADMIN LOGIN ROUTE ---
@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email, password = request.form['email'], request.form['password']
        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE email = ? AND password = ? AND role = 'admin'", (email, password)).fetchone()
        conn.close()
        
        if user:
            session['user_id'], session['user_role'], session['user_email'], session['user_name'] = user['id'], user['role'], user['email'], user['name']
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template('admin_login.html', error="Access Denied. Invalid Admin Credentials.")
    return render_template('admin_login.html')

@app.route('/logout')
def logout():
    session.clear() 
    return redirect(url_for('home'))

# --- DASHBOARD ROUTES ---
@app.route('/doctor_dashboard')
def doctor_dashboard():
    if 'user_id' not in session or session['user_role'] != 'doctor': return redirect(url_for('login'))
    conn = get_db_connection()
    records = conn.execute('SELECT * FROM records WHERE doctor_email = ? ORDER BY timestamp DESC', (session['user_email'],)).fetchall()
    conn.close()
    return render_template('doctor_dashboard.html', name=session['user_name'], email=session['user_email'], records=records)

@app.route('/patient_dashboard')
def patient_dashboard():
    if 'user_id' not in session or session['user_role'] != 'patient': return redirect(url_for('login'))
    conn = get_db_connection()
    records = conn.execute('SELECT * FROM records WHERE patient_email = ? ORDER BY timestamp DESC', (session['user_email'],)).fetchall()
    conn.close()
    return render_template('patient_dashboard.html', name=session['user_name'], email=session['user_email'], records=records)

@app.route('/admin_dashboard')
def admin_dashboard():
    if 'user_id' not in session or session['user_role'] != 'admin': return redirect(url_for('admin_login'))
    conn = get_db_connection()
    query = '''SELECT p.id as pending_id, p.proposed_diagnosis, p.doctor_email as requesting_doctor, r.patient_email, r.age, r.chol, r.ai_prediction as original_prediction FROM pending_corrections p JOIN records r ON p.record_id = r.id WHERE p.status = 'pending' '''
    pending_records = conn.execute(query).fetchall()
    conn.close()
    return render_template('admin_dashboard.html', name=session['user_name'], records=pending_records)

# --- CORE API ENDPOINTS (Untouched) ---
@app.route('/predict_and_save', methods=['POST'])
def predict_and_save():
    if 'user_role' not in session or session['user_role'] != 'doctor': return jsonify({"error": "Unauthorized"}), 403
    data = request.get_json()
    patient_email = data.pop('patient_email') 
    df = pd.DataFrame([data])
    result = int(model.predict(scaler.transform(df))[0]) 
    
    conn = get_db_connection()
    conn.execute('''INSERT INTO records (doctor_email, patient_email, age, sex, cp, trestbps, chol, fbs, restecg, thalach, exang, oldpeak, slope, ca, thal, ai_prediction) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                 (session['user_email'], patient_email, data['age'], data['sex'], data['cp'], data['trestbps'], data['chol'], data['fbs'], data['restecg'], data['thalach'], data['exang'], data['oldpeak'], data['slope'], data['ca'], data['thal'], result))
    conn.commit(); conn.close()
    return jsonify({"risk_prediction": result})

@app.route('/bulk_upload', methods=['POST'])
def bulk_upload():
    if 'user_role' not in session or session['user_role'] != 'doctor': return redirect(url_for('login'))
    file = request.files['file']
    if not file: return redirect(url_for('doctor_dashboard'))
    try:
        df = pd.read_csv(file)
        conn = get_db_connection()
        for index, row in df.iterrows():
            patient_email = row['patient_email']
            vitals = row.drop('patient_email')
            result = int(model.predict(scaler.transform(pd.DataFrame([vitals])))[0])
            conn.execute('''INSERT INTO records (doctor_email, patient_email, age, sex, cp, trestbps, chol, fbs, restecg, thalach, exang, oldpeak, slope, ca, thal, ai_prediction) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                         (session['user_email'], patient_email, row['age'], row['sex'], row['cp'], row['trestbps'], row['chol'], row['fbs'], row['restecg'], row['thalach'], row['exang'], row['oldpeak'], row['slope'], row['ca'], row['thal'], result))
        conn.commit(); conn.close()
        return redirect(url_for('doctor_dashboard'))
    except Exception as e: return f"Error processing CSV: {e}"

@app.route('/feedback', methods=['POST'])
def feedback():
    if 'user_role' not in session or session['user_role'] != 'doctor': return jsonify({"error": "Unauthorized"}), 403
    data = request.get_json()
    conn = get_db_connection()
    conn.execute('INSERT INTO pending_corrections (record_id, doctor_email, proposed_diagnosis) VALUES (?, ?, ?)', (data.get('record_id'), session['user_email'], data.get('correct_diagnosis')))
    conn.commit(); conn.close()
    return jsonify({"message": "Correction submitted to Super Admin."})

@app.route('/approve_correction', methods=['POST'])
def approve_correction():
    if 'user_role' not in session or session['user_role'] != 'admin': return jsonify({"error": "Unauthorized"}), 403
    pending_id = request.get_json().get('pending_id')
    conn = get_db_connection()
    pending = conn.execute('SELECT * FROM pending_corrections WHERE id = ?', (pending_id,)).fetchone()
    if pending:
        record_id, new_diagnosis = pending['record_id'], pending['proposed_diagnosis']
        record = conn.execute('SELECT age, sex, cp, trestbps, chol, fbs, restecg, thalach, exang, oldpeak, slope, ca, thal FROM records WHERE id = ?', (record_id,)).fetchone()
        model.partial_fit(scaler.transform(pd.DataFrame([dict(record)])), [new_diagnosis])
        joblib.dump(model, "heart_disease_brain.joblib")
        conn.execute('UPDATE records SET ai_prediction = ? WHERE id = ?', (new_diagnosis, record_id))
        conn.execute("UPDATE pending_corrections SET status = 'approved' WHERE id = ?", (pending_id,))
        conn.commit()
    conn.close()
    return jsonify({"message": "Approved! AI retrained."})

@app.route('/reject_correction', methods=['POST'])
def reject_correction():
    if 'user_role' not in session or session['user_role'] != 'admin': return jsonify({"error": "Unauthorized"}), 403
    conn = get_db_connection()
    conn.execute("UPDATE pending_corrections SET status = 'rejected' WHERE id = ?", (request.get_json().get('pending_id'),))
    conn.commit(); conn.close()
    return jsonify({"message": "Rejected! AI protected."})

@app.route('/update_profile', methods=['POST'])
def update_profile():
    if 'user_id' not in session: return jsonify({"error": "Unauthorized"}), 403
    data = request.get_json()
    new_name, new_email, new_password = data.get('name'), data.get('email'), data.get('password') 
    conn = get_db_connection()
    try:
        if new_password: conn.execute('UPDATE users SET name = ?, email = ?, password = ? WHERE id = ?', (new_name, new_email, new_password, session['user_id']))
        else: conn.execute('UPDATE users SET name = ?, email = ? WHERE id = ?', (new_name, new_email, session['user_id']))
        
        if session['user_role'] == 'doctor' and new_email != session['user_email']:
            conn.execute('UPDATE records SET doctor_email = ? WHERE doctor_email = ?', (new_email, session['user_email']))
            conn.execute('UPDATE pending_corrections SET doctor_email = ? WHERE doctor_email = ?', (new_email, session['user_email']))
        elif session['user_role'] == 'patient' and new_email != session['user_email']:
            conn.execute('UPDATE records SET patient_email = ? WHERE patient_email = ?', (new_email, session['user_email']))
                         
        conn.commit()
        session['user_name'], session['user_email'] = new_name, new_email
        return jsonify({"message": "Profile updated!"})
    except sqlite3.IntegrityError: return jsonify({"error": "Email already in use."}), 400
    finally: conn.close()

# --- GEMINI CHATBOT ROUTE (UNTOUCHED AND FULLY WORKING) ---
@app.route('/api/chat', methods=['POST'])
def api_chat():
    if 'user_role' not in session: return jsonify({"error": "Unauthorized"}), 403
    
    data = request.get_json()
    user_msg = data.get('message', '')
    lang_code = data.get('language', 'en-IN')
    chat_history = data.get('history', []) 
    
    language_map = {
        'en-IN': 'Standard English (Use correct English spelling and grammar, do NOT use Hindi words)',
        'hi-IN': 'Hindi (in Devanagari script)',
        'kn-IN': 'Kannada (in Kannada script)',
        'te-IN': 'Telugu (in Telugu script)',
        'ta-IN': 'Tamil (in Tamil script)'
    }
    strict_language = language_map.get(lang_code, 'Standard English')

    conn = get_db_connection()
    records = conn.execute('SELECT trestbps, chol, thalach, ai_prediction, timestamp FROM records WHERE patient_email = ? ORDER BY timestamp DESC LIMIT 3', (session['user_email'],)).fetchall()
    conn.close()
    
    med_history = "No past hospital records found."
    if records:
        med_history = "\n".join([f"Date: {r['timestamp'][:10]}, BP: {r['trestbps']}, Chol: {r['chol']}, Heart Rate: {r['thalach']}, Risk: {'High' if r['ai_prediction']==1 else 'Healthy'}" for r in records])

    system_instruction = f"""
    You are CardioCare AI, a caring, professional cardiologist.
    Patient's name: {session['user_name']}. 
    Medical History: {med_history}

    CRITICAL RULES:
    1. Reply entirely and strictly in {strict_language}.
    2. Keep answers EXTREMELY SHORT (1 or 2 sentences max). Be concise.
    3. Do NOT use markdown headers, asterisks, or bullet points. Use plain text only.
    """

    try:
        formatted_history = []
        for msg in chat_history:
            role = "user" if msg['role'] == 'user' else "model"
            formatted_history.append(types.Content(role=role, parts=[types.Part.from_text(text=msg['text'])]))
            
        config = types.GenerateContentConfig(system_instruction=system_instruction)
        chat = gemini_client.chats.create(model='gemini-2.5-flash', config=config, history=formatted_history)
        reply_text = chat.send_message(user_msg).text
        
        tts_lang = lang_code.split('-')[0]
        if tts_lang not in ['en', 'hi', 'kn', 'te', 'ta']:
            tts_lang = 'en'
            
        clean_text = reply_text.replace('*', '').replace('#', '').replace('\n', ' ')
        sentences = re.split(r'(?<=[.!?।]) +', clean_text)
        
        audio_fp = io.BytesIO()
        audio_success = False
        
        try:
            for sentence in sentences:
                if len(sentence.strip()) > 0:
                    tts = gTTS(text=sentence.strip(), lang=tts_lang, slow=False)
                    tts.write_to_fp(audio_fp)
            
            audio_fp.seek(0)
            audio_b64 = base64.b64encode(audio_fp.read()).decode('utf-8')
            audio_success = True
        except Exception as e:
            print("gTTS Blocked/Failed:", e)
            audio_b64 = None

        return jsonify({
            "reply": reply_text,
            "audio": audio_b64 if audio_success else None
        })
        
    except Exception as e:
        print("Gemini API Error:", e)
        return jsonify({"reply": "System Error: Unable to connect to intelligence servers. Please check your terminal.", "audio": None})

if __name__ == '__main__':
    app.run(debug=True)
