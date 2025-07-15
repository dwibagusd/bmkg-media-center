# Import Library
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file, g
from datetime import datetime
import os
import io
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from supabase import create_client, Client
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'supersecretkey')
app.config['UPLOAD_FOLDER'] = 'static/uploads/'  # Folder for uploads
app.config['DATABASE'] = 'bmkg_media.db'         # SQLite database file
app.config['ALLOWED_EXTENSIONS'] = {'wav', 'mp3', 'ogg'}
app.config['WHATSAPP_ADMIN'] = '6281932689046'
app.config['WHATSAPP_DEFAULT_MSG'] = 'Halo BMKG, saya ingin konfirmasi permohonan wawancara dengan token: '

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Configure Supabase (for storage only)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Utility: allowed file extensions
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Database connection (SQLite)
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = sqlite3.connect(app.config['DATABASE'])
        db.row_factory = sqlite3.Row
        g._database = db
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# Initialize / create tables
def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        # Create users table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        )''')
        # Create interview_requests table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS interview_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT UNIQUE NOT NULL,
            interviewer_name TEXT NOT NULL,
            media_name TEXT NOT NULL,
            topic TEXT NOT NULL,
            method TEXT NOT NULL,
            datetime TEXT NOT NULL,
            meeting_link TEXT,
            whatsapp_link TEXT,
            status TEXT DEFAULT 'Pending',
            request_date TEXT NOT NULL
        )''')
        # Create audio_recordings table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS audio_recordings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT NOT NULL,
            interviewee TEXT NOT NULL,
            interviewer TEXT NOT NULL,
            date TEXT NOT NULL,
            filename TEXT NOT NULL,
            transcript TEXT,
            FOREIGN KEY (token) REFERENCES interview_requests (token)
        )''')
        # Insert default users if not exist
        try:
            cursor.execute('INSERT INTO users (username, password, role) VALUES (?, ?, ?)',
                           ('admin', generate_password_hash('password123'), 'admin'))
            cursor.execute('INSERT INTO users (username, password, role) VALUES (?, ?, ?)',
                           ('user1', generate_password_hash('user123'), 'user'))
        except sqlite3.IntegrityError:
            pass
        db.commit()

# In-memory defaults (for homepage, warnings, etc.)
weather_data = { ... }  # keep as-is
warnings = [ ... ]
press_releases = [ ... ]

# Helper to generate 8-char token
def generate_token():
    import random, string
    return ''.join(random.choices('ABCDEFGHJKLMNPQRSTUVWXYZ23456789', k=8))

# =========================================
# Routes
# =========================================

@app.route('/')
def index():
    return render_template('index.html', 
                           press_releases=press_releases[:3],
                           weather=weather_data['today'],
                           warnings=warnings)

@app.route('/press-release/<int:release_id>')
def press_release_detail(release_id):
    release = next((r for r in press_releases if r['id'] == release_id), None)
    if not release:
        flash('Press release not found', 'danger')
        return redirect(url_for('index'))
    return render_template('press_release_detail.html', release=release)

@app.route('/request-interview', methods=['GET', 'POST'])
def request_interview():
    if request.method == 'POST':
        token = generate_token()
        method = request.form.get('method')
        whatsapp_link = ''
        if method == 'whatsapp':
            msg = f"{app.config['WHATSAPP_DEFAULT_MSG']}{token}"
            whatsapp_link = f"https://wa.me/{app.config['WHATSAPP_ADMIN']}?text={msg}"
        data = {
            'token': token,
            'interviewer_name': request.form['interviewer_name'],
            'media_name': request.form['media_name'],
            'topic': request.form['topic'],
            'method': method,
            'datetime': request.form['datetime'],
            'meeting_link': request.form.get('meeting_link',''),
            'whatsapp_link': whatsapp_link,
            'request_date': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'status': 'Pending'
        }
        db = get_db()
        cur = db.cursor()
        cur.execute('''
            INSERT INTO interview_requests
            (token, interviewer_name, media_name, topic, method, datetime, meeting_link, whatsapp_link, request_date, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', tuple(data.values()))
        db.commit()
        if method == 'whatsapp':
            return redirect(whatsapp_link)
        flash(f"Permohonan wawancara berhasil! Token Anda: {token}", 'success')
        return redirect(url_for('request_interview'))
    return render_template('request_interview.html')

@app.route('/historical-data')
def historical_data_view():
    if 'user' not in session:
        flash('Harap login terlebih dahulu', 'danger')
        return redirect(url_for('login'))
    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT * FROM interview_requests ORDER BY request_date DESC')
    requests = cur.fetchall()
    return render_template('historical_data.html', historical_data=requests)

@app.route('/recorder', methods=['GET','POST'])
def recorder():
    if request.method == 'POST':
        if 'audio_file' not in request.files:
            flash('No file uploaded', 'danger')
            return redirect(url_for('recorder'))
        file = request.files['audio_file']
        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(url_for('recorder'))
        if allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_bytes = file.read()
            # Upload to Supabase Storage
            supabase.storage().from_('audios').upload(filename, file_bytes)
            # Save metadata in SQLite
            db = get_db()
            cur = db.cursor()
            cur.execute('''INSERT INTO audio_recordings
                        (token, interviewee, interviewer, date, filename, transcript)
                        VALUES (?, ?, ?, ?, ?, ?)''', (
                        request.form['token'],
                        request.form['interviewee'],
                        request.form['interviewer'],
                        datetime.now().strftime('%Y-%m-%d %H:%M'),
                        filename,
                        request.form.get('transcript','')
            ))
            db.commit()
            flash('File berhasil diupload!', 'success')
        return redirect(url_for('recorder'))
    return render_template('recorder.html')

@app.route('/generate-pdf/<int:recording_id>')
def generate_pdf(recording_id):
    if 'user' not in session:
        flash('Unauthorized access', 'danger')
        return redirect(url_for('login'))
    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT role FROM users WHERE username = ?', (session['user'],))
    row = cur.fetchone()
    if not row or row['role'] != 'admin':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('index'))
    cur.execute('SELECT * FROM audio_recordings WHERE id = ?', (recording_id,))
    rec = cur.fetchone()
    if not rec:
        flash('Recording not found', 'danger')
        return redirect(url_for('recorder'))
    # Build PDF
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    p.setFont("Helvetica-Bold", 16)
    p.drawString(100, 750, "Laporan Wawancara BMKG")
    p.setFont("Helvetica", 12)
    p.drawString(100, 720, f"Token: {rec['token']}")
    p.drawString(100, 700, f"Tanggal: {rec['date']}")
    p.drawString(100, 680, f"Pewawancara: {rec['interviewer']}")
    p.drawString(100, 660, f"Narasumber: {rec['interviewee']}")
    p.drawString(100, 620, "Transkrip Wawancara:")
    text = p.beginText(100, 600)
    text.setFont("Helvetica", 10)
    for line in rec['transcript'].split('\n'):
        for part in [line[i:i+80] for i in range(0, len(line), 80)]:
            text.textLine(part)
    p.drawText(text)
    p.showPage()
    p.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True,
                     download_name=f"transkrip_{rec['token']}.pdf",
                     mimetype='application/pdf')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        cur = db.cursor()
        cur.execute('SELECT * FROM users WHERE username = ?', (username,))
        user = cur.fetchone()
        if user and check_password_hash(user['password'], password):
            session['user'] = user['username']
            flash('Login berhasil!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Username atau password salah', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('index'))

if __name__ == "__main__":
    from waitress import serve
    init_db()
    serve(app, host="0.0.0.0", port=8080)
