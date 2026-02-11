import sqlite3
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import os
import random
import datetime

app = Flask(__name__)
app.secret_key = 'cabbage_secret_key'

# --- แก้ไข 1: ตั้งค่า Path ให้ถูกต้องสำหรับ PythonAnywhere ---
# หาที่อยู่ของไฟล์ app.py ปัจจุบัน
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# กำหนดที่อยู่ Database แบบระบุเต็ม
DB_PATH = os.path.join(BASE_DIR, 'cabbage.db')
# กำหนดที่อยู่โฟลเดอร์รูปภาพ
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static/uploads')

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def get_db_connection():
    # ใช้ DB_PATH ที่ระบุที่อยู่เต็มแล้ว
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, password TEXT, role TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS content (key TEXT PRIMARY KEY, text_content TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS upload_logs 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, date_upload DATE, status TEXT, weeks INTEGER)''')
    
    # สร้าง Admin
    c.execute("SELECT * FROM users WHERE email = 'admin01@gmail.com'")
    if not c.fetchone():
        c.execute("INSERT INTO users (email, password, role) VALUES (?, ?, ?)", 
                  ('admin01@gmail.com', '12345678', 'admin'))
    
    conn.commit()
    conn.close()

# เรียกใช้เพื่อสร้าง DB (ถ้ายังไม่มี)
init_db()

# --- Routes ---

@app.route('/')
def index():
    conn = get_db_connection()
    ann_row = conn.execute("SELECT text_content FROM content WHERE key='announcement'").fetchone()
    announcement_text = ann_row['text_content'] if ann_row else ""
    man_row = conn.execute("SELECT text_content FROM content WHERE key='manual'").fetchone()
    manual_text = man_row['text_content'] if man_row else ""
    conn.close()
    
    user_email = session.get('email')
    return render_template('index.html', announcement=announcement_text, manual=manual_text, user_email=user_email)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE email = ? AND password = ?', (email, password)).fetchone()
        conn.close()

        if user:
            session['user_id'] = user['id']
            session['email'] = user['email']
            session['role'] = user['role']
            
            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('index'))
        else:
            return render_template('login.html', error="อีเมลหรือรหัสผ่านไม่ถูกต้อง")
            
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        conn = get_db_connection()
        try:
            conn.execute('INSERT INTO users (email, password, role) VALUES (?, ?, ?)', (email, password, 'user'))
            conn.commit()
            conn.close()
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            conn.close()
            return render_template('register.html', error="อีเมลนี้ถูกใช้งานแล้ว")
            
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/admin')
def admin_dashboard():
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))

    conn = get_db_connection()
    users = conn.execute('SELECT * FROM users').fetchall()
    
    # ดึงข้อมูลมาแสดงผล (Stats)
    today = datetime.date.today()
    start_month = today.replace(day=1)
    start_year = today.replace(month=1, day=1)

    # ใช้ try-except ป้องกัน error หากตารางยังไม่สมบูรณ์
    try:
        count_today = conn.execute("SELECT COUNT(*) FROM upload_logs WHERE date_upload = ?", (today,)).fetchone()[0]
        count_month = conn.execute("SELECT COUNT(*) FROM upload_logs WHERE date_upload >= ?", (start_month,)).fetchone()[0]
        count_year = conn.execute("SELECT COUNT(*) FROM upload_logs WHERE date_upload >= ?", (start_year,)).fetchone()[0]
        avg_weeks = conn.execute("SELECT AVG(weeks) FROM upload_logs").fetchone()[0] or 0
    except:
        count_today, count_month, count_year, avg_weeks = 0, 0, 0, 0

    settings = conn.execute('SELECT * FROM settings').fetchall()
    settings_dict = {row['key']: row['value'] for row in settings}
    contents = conn.execute('SELECT * FROM content').fetchall()
    content_dict = {row['key']: row['text_content'] for row in contents}
    
    conn.close()

    return render_template('admin.html', 
                           users=users, 
                           settings=settings_dict, 
                           content=content_dict,
                           stats={'today': count_today, 'month': count_month, 'year': count_year, 'avg_weeks': round(avg_weeks, 1)})

@app.route('/admin/user/<action>', methods=['POST'])
def manage_user(action):
    if 'role' not in session or session['role'] != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
    
    conn = get_db_connection()
    if action == 'add':
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']
        try:
            conn.execute('INSERT INTO users (email, password, role) VALUES (?, ?, ?)', (email, password, role))
            conn.commit()
        except sqlite3.IntegrityError:
             conn.close()
             return jsonify({'error': 'Email already exists'}), 400
    elif action == 'delete':
        user_id = request.form['user_id']
        conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.commit()
    
    conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/save_settings', methods=['POST'])
def save_settings():
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    file_size = request.form.get('max_file_size')
    file_type = request.form.get('allowed_file_types')
    conn.execute('REPLACE INTO settings (key, value) VALUES (?, ?)', ('max_file_size', file_size))
    conn.execute('REPLACE INTO settings (key, value) VALUES (?, ?)', ('allowed_file_types', file_type))
    
    manual = request.form.get('manual_text')
    announcement = request.form.get('announcement_text')
    conn.execute('REPLACE INTO content (key, text_content) VALUES (?, ?)', ('manual', manual))
    conn.execute('REPLACE INTO content (key, text_content) VALUES (?, ?)', ('announcement', announcement))
    
    conn.commit()
    conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/analyze', methods=['POST'])
def analyze():
    if 'file' not in request.files: return jsonify({'error': 'No file'}), 400
    file = request.files['file']
    if file.filename == '': return jsonify({'error': 'No selected file'}), 400

    if file:
        filename = file.filename
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        # AI Simulation
        time.sleep(1)
        statuses = ['ready', 'not-ready', 'overdue']
        result_status = random.choice(statuses)
        weeks = 0
        
        if result_status == 'ready':
            weeks = random.randint(6, 8)
            response_data = {'status': 'ready', 'label': 'พร้อมเก็บเกี่ยว', 'description': 'AI ตรวจพบหัวกะหล่ำแน่น ขนาดเหมาะสม', 'weeks': weeks, 'icon': 'fas fa-check-circle'}
        elif result_status == 'overdue':
            weeks = random.randint(9, 10)
            response_data = {'status': 'overdue', 'label': 'เกินเวลาแล้ว', 'description': 'กะหล่ำปลีเริ่มแก่เกินไป ใบเริ่มเหลือง', 'weeks': weeks, 'icon': 'fas fa-exclamation-triangle'}
        else:
            weeks = random.randint(2, 5)
            response_data = {'status': 'not-ready', 'label': 'ยังไม่พร้อม', 'description': 'หัวยังไม่แน่นพอ ควรรออีกสักพัก', 'weeks': weeks, 'icon': 'fas fa-clock'}
            
        # ส่ง Path กลับไปให้ Frontend (ต้องเป็น Path สัมพัทธ์สำหรับ Web)
        response_data['image_url'] = f"/static/uploads/{filename}"

        conn = get_db_connection()
        conn.execute('INSERT INTO upload_logs (date_upload, status, weeks) VALUES (?, ?, ?)', 
                     (datetime.date.today(), result_status, weeks))
        conn.commit()
        conn.close()
        
        return jsonify(response_data)

import time

if __name__ == '__main__':
    app.run(debug=True)