import sqlite3
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import os
import random
import datetime

app = Flask(__name__)
app.secret_key = 'cabbage_secret_key'  # จำเป็นสำหรับการ Login

# ตั้งค่าเริ่มต้น
UPLOAD_FOLDER = 'static/uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- ส่วนจัดการฐานข้อมูล (Database) ---
def init_db():
    conn = sqlite3.connect('cabbage.db')
    c = conn.cursor()
    
    # 1. ตาราง Users (เก็บข้อมูลแอดมินและผู้ใช้)
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE, password TEXT, role TEXT)''')
    
    # 2. ตาราง Settings (เก็บค่า config ต่างๆ)
    c.execute('''CREATE TABLE IF NOT EXISTS settings 
                 (key TEXT PRIMARY KEY, value TEXT)''')
    
    # 3. ตาราง Content (เก็บประกาศ คู่มือ)
    c.execute('''CREATE TABLE IF NOT EXISTS content 
                 (key TEXT PRIMARY KEY, text_content TEXT)''')

    # 4. ตาราง Logs (เก็บประวัติการอัปโหลดเพื่อดูสถิติ)
    c.execute('''CREATE TABLE IF NOT EXISTS upload_logs 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, date_upload DATE, status TEXT, weeks INTEGER)''')

    # สร้าง Admin คนแรก (ถ้ายังไม่มี)
    c.execute("SELECT * FROM users WHERE email = 'admin01@gmail.com'")
    if not c.fetchone():
        c.execute("INSERT INTO users (email, password, role) VALUES (?, ?, ?)", 
                  ('admin01@gmail.com', '12345678', 'admin'))
        print("สร้าง Admin เรียบร้อย: admin01@gmail.com")

    conn.commit()
    conn.close()

# เรียกใช้งานฟังก์ชันสร้างฐานข้อมูลทันทีที่รันโปรแกรม
init_db()

# ฟังก์ชันเชื่อมต่อฐานข้อมูล
def get_db_connection():
    conn = sqlite3.connect('cabbage.db')
    conn.row_factory = sqlite3.Row
    return conn

# --- Routes (เส้นทางเว็บไซต์) ---

#  index ให้ดึงทั้งประกาศและคู่มือส่งไปหน้าเว็บ
@app.route('/')
def index():
    conn = get_db_connection()
    
    # 1. ดึงประกาศ
    ann_row = conn.execute("SELECT text_content FROM content WHERE key='announcement'").fetchone()
    announcement_text = ann_row['text_content'] if ann_row else ""
    
    # 2. ดึงคู่มือ/เงื่อนไข
    man_row = conn.execute("SELECT text_content FROM content WHERE key='manual'").fetchone()
    manual_text = man_row['text_content'] if man_row else ""
    
    conn.close()
    
    # ส่งตัวแปร announcement และ manual ไปที่ไฟล์ index.html
    return render_template('index.html', announcement=announcement_text, manual=manual_text)

# หน้า Login
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
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template('login.html', error="อีเมลหรือรหัสผ่านไม่ถูกต้อง")
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# หน้า Admin Dashboard (รวมทุกอย่างตามโจทย์)
@app.route('/admin')
def admin_dashboard():
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))

    conn = get_db_connection()
    
    # 1. ข้อมูล Users
    users = conn.execute('SELECT * FROM users').fetchall()
    
    # 2. ข้อมูล Settings
    settings = conn.execute('SELECT * FROM settings').fetchall()
    settings_dict = {row['key']: row['value'] for row in settings}
    
    # 3. ข้อมูล Content
    contents = conn.execute('SELECT * FROM content').fetchall()
    content_dict = {row['key']: row['text_content'] for row in contents}

    # 4. สถิติ (Stats)
    today = datetime.date.today()
    start_month = today.replace(day=1)
    start_year = today.replace(month=1, day=1)

    count_today = conn.execute("SELECT COUNT(*) FROM upload_logs WHERE date_upload = ?", (today,)).fetchone()[0]
    count_month = conn.execute("SELECT COUNT(*) FROM upload_logs WHERE date_upload >= ?", (start_month,)).fetchone()[0]
    count_year = conn.execute("SELECT COUNT(*) FROM upload_logs WHERE date_upload >= ?", (start_year,)).fetchone()[0]
    avg_weeks = conn.execute("SELECT AVG(weeks) FROM upload_logs").fetchone()[0] or 0

    conn.close()

    return render_template('admin.html', 
                           users=users, 
                           settings=settings_dict, 
                           content=content_dict,
                           stats={'today': count_today, 'month': count_month, 'year': count_year, 'avg_weeks': round(avg_weeks, 1)})

# API: จัดการ User (เพิ่ม/ลบ)
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

# API: บันทึกการตั้งค่า (Settings & Content)
@app.route('/admin/save_settings', methods=['POST'])
def save_settings():
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    
    # Save Configs
    file_size = request.form.get('max_file_size')
    file_type = request.form.get('allowed_file_types')
    conn.execute('REPLACE INTO settings (key, value) VALUES (?, ?)', ('max_file_size', file_size))
    conn.execute('REPLACE INTO settings (key, value) VALUES (?, ?)', ('allowed_file_types', file_type))
    
    # Save Content
    manual = request.form.get('manual_text')
    announcement = request.form.get('announcement_text')
    conn.execute('REPLACE INTO content (key, text_content) VALUES (?, ?)', ('manual', manual))
    conn.execute('REPLACE INTO content (key, text_content) VALUES (?, ?)', ('announcement', announcement))
    
    conn.commit()
    conn.close()
    return redirect(url_for('admin_dashboard'))

# API Analyze (ตัวเดิม แต่เพิ่มการบันทึกสถิติลง DB)
@app.route('/analyze', methods=['POST'])
def analyze():
    # (โค้ดเดิมส่วนตรวจสอบไฟล์...)
    if 'file' not in request.files: return jsonify({'error': 'No file'}), 400
    file = request.files['file']
    if file.filename == '': return jsonify({'error': 'No selected file'}), 400

    if file:
        filename = file.filename
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        # Logic AI เดิม
        statuses = ['ready', 'not-ready', 'overdue']
        result_status = random.choice(statuses)
        weeks = 0
        
        if result_status == 'ready':
            weeks = random.randint(6, 8)
            response_data = {'status': 'ready', 'label': 'พร้อมเก็บเกี่ยว', 'description': '...', 'weeks': weeks, 'icon': 'fas fa-check-circle'}
        elif result_status == 'overdue':
            weeks = random.randint(9, 10)
            response_data = {'status': 'overdue', 'label': 'เกินเวลาแล้ว', 'description': '...', 'weeks': weeks, 'icon': 'fas fa-exclamation-triangle'}
        else:
            weeks = random.randint(2, 5)
            response_data = {'status': 'not-ready', 'label': 'ยังไม่พร้อม', 'description': '...', 'weeks': weeks, 'icon': 'fas fa-clock'}
            
        response_data['image_url'] = f"/{filepath}"

        # --- เพิ่ม: บันทึกสถิติลง DB ---
        conn = get_db_connection()
        conn.execute('INSERT INTO upload_logs (date_upload, status, weeks) VALUES (?, ?, ?)', 
                     (datetime.date.today(), result_status, weeks))
        conn.commit()
        conn.close()
        
        return jsonify(response_data)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)