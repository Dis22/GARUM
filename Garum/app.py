import sqlite3
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import os
import random
import datetime
import time
# --- ส่วนที่เพิ่มเข้ามาสำหรับ AI ---
import cv2
import numpy as np
from ultralytics import YOLO
# -----------------------------

app = Flask(__name__)
app.secret_key = 'cabbage_secret_key'

# --- ตั้งค่า Path ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'cabbage.db')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static/uploads')

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- โหลดโมเดล AI เตรียมไว้ ---
print("⏳ กำลังโหลดโมเดล AI...")
try:
    # ตรวจสอบว่ามีไฟล์ best.pt อยู่ไหม
    MODEL_PATH = os.path.join(BASE_DIR, 'best.pt')
    if os.path.exists(MODEL_PATH):
        model = YOLO(MODEL_PATH)
        print("✅ โหลดโมเดลสำเร็จ!")
    else:
        print("⚠️ หาไฟล์ best.pt ไม่เจอ! (ระบบจะกลับไปใช้การสุ่มชั่วคราว)")
        model = None
except Exception as e:
    print(f"❌ Error โหลดโมเดลไม่ได้: {e}")
    model = None
# ---------------------------

def get_db_connection():
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

# เรียกใช้เพื่อสร้าง DB
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
    
    today = datetime.date.today()
    start_month = today.replace(day=1)
    start_year = today.replace(month=1, day=1)

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

# ======================================================
# ส่วนวิเคราะห์ด้วย AI (แทนที่ Random เดิม)
# ======================================================
@app.route('/analyze', methods=['POST'])
def analyze():
    if 'file' not in request.files: return jsonify({'error': 'No file'}), 400
    file = request.files['file']
    if file.filename == '': return jsonify({'error': 'No selected file'}), 400

    if file:
        filename = file.filename
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        # ค่าเริ่มต้น (กรณี AI มีปัญหา หรือไม่เจออะไร)
        final_status = 'not-ready'
        final_label = 'ตรวจไม่พบ'
        final_desc = 'ไม่พบหัวกะหล่ำปลีในภาพ'
        avg_weeks = 0
        final_icon = 'fas fa-question-circle'

        # --- เริ่มใช้ AI ---
        if model:
            try:
                # 1. อ่านรูปด้วย OpenCV
                img = cv2.imread(filepath)
                
                # 2. ให้ AI ทำนาย (conf=0.4 คือต้องมั่นใจ 40% ขึ้นไป)
                results = model(img, conf=0.4)

                detected_weeks = []
                count_ready = 0
                count_not_ready = 0

                # 3. วาดกรอบและนับจำนวน
                for result in results:
                    for box in result.boxes:
                        cls_id = int(box.cls[0]) 
                        # x1, y1, x2, y2 = map(int, box.xyxy[0]) # ถ้าอยากวาดกรอบให้เปิดบรรทัดนี้

                        # แปลง Class ID เป็น Week (0->1, ... 7->8)
                        week_num = cls_id + 1
                        detected_weeks.append(week_num)

                        if week_num >= 8: # Week 8 = Ready
                            count_ready += 1
                            # cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2) # สีเขียว
                        else:
                            count_not_ready += 1
                            # cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 2) # สีแดง

                # 4. บันทึกรูปที่วาดกรอบแล้วทับไฟล์เดิม (ถ้าเปิดวาดกรอบ)
                # cv2.imwrite(filepath, img)

                # 5. สรุปผล
                if detected_weeks:
                    avg_weeks = round(sum(detected_weeks) / len(detected_weeks))
                    
                    if count_ready > count_not_ready:
                        final_status = 'ready'
                        final_label = 'พร้อมเก็บเกี่ยว'
                        final_desc = f'พบกะหล่ำพร้อมเก็บ {count_ready} หัว (เฉลี่ย Week {avg_weeks})'
                        final_icon = 'fas fa-check-circle'
                    else:
                        final_status = 'not-ready'
                        final_label = 'ยังไม่พร้อม'
                        final_desc = f'ส่วนใหญ่ยังโตไม่เต็มที่ (เฉลี่ย Week {avg_weeks})'
                        final_icon = 'fas fa-clock'
                        
            except Exception as e:
                print(f"AI Error: {e}")
                final_desc = "เกิดข้อผิดพลาดในการวิเคราะห์ภาพ"

        else:
            # กรณีไม่มีโมเดล ให้ใช้ Random แก้ขัดไปก่อน (เหมือนโค้ดเดิม)
            statuses = ['ready', 'not-ready', 'overdue']
            final_status = random.choice(statuses)
            if final_status == 'ready':
                avg_weeks = random.randint(7, 8)
                final_label = 'พร้อมเก็บเกี่ยว (จำลอง)'
                final_desc = 'AI จำลอง: พบหัวกะหล่ำแน่น'
                final_icon = 'fas fa-check-circle'
            else:
                avg_weeks = random.randint(3, 6)
                final_label = 'ยังไม่พร้อม (จำลอง)'
                final_desc = 'AI จำลอง: หัวยังไม่แน่น'
                final_icon = 'fas fa-clock'

        # บันทึกลง Database
        conn = get_db_connection()
        conn.execute('INSERT INTO upload_logs (date_upload, status, weeks) VALUES (?, ?, ?)', 
                     (datetime.date.today(), final_status, avg_weeks))
        conn.commit()
        conn.close()
        
        # ส่ง JSON กลับไป
        response_data = {
            'status': final_status,
            'label': final_label,
            'description': final_desc,
            'weeks': avg_weeks,
            'icon': final_icon,
            'image_url': f"/static/uploads/{filename}?t={int(time.time())}"
        }
        
        return jsonify(response_data)

if __name__ == '__main__':
    # รันบน Render ต้องระบุ host='0.0.0.0'
    app.run(host='0.0.0.0', port=5000, debug=True)