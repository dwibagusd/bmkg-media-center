# Import Library
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from datetime import datetime, timedelta
import os
import json
import random
from werkzeug.utils import secure_filename
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import io
import sqlite3
from flask import g
import pymysql, psycopg2 # untuk PostgreSQL
from werkzeug.security import generate_password_hash, check_password_hash
from supabase import create_client, Client

app = Flask(__name__)
app.secret_key = 'supersecretkey'
app.config['UPLOAD_FOLDER'] = 'static/uploads/'
app.config['DATABASE'] = 'bmkg_media.db'
app.config['ALLOWED_EXTENSIONS'] = {'wav', 'mp3', 'ogg'}
app.config['WHATSAPP_ADMIN'] = '6281932689046'  # Nomor WhatsApp admin dengan kode negara
app.config['WHATSAPP_DEFAULT_MSG'] = 'Halo BMKG, saya ingin konfirmasi permohonan wawancara dengan token: '

# Buat folder unggahan
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Konfigurasi Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL")  # Akan di-set di Vercel
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")  # Akan di-set di Vercel
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


# Konfigurasi database
DATABASE = 'bmkg_media.db'

def get_db():
    return supabase

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# def init_db():
#     with app.app_context():
#         db = get_db()
#         cursor = db.cursor()
        
#         # Buat tabel jika belum ada
#         cursor.execute('''
#         CREATE TABLE IF NOT EXISTS users (
#             id INTEGER PRIMARY KEY AUTOINCREMENT,
#             username TEXT UNIQUE NOT NULL,
#             password TEXT NOT NULL,
#             role TEXT NOT NULL
#         )
#         ''')
        
#         cursor.execute('''
#         CREATE TABLE IF NOT EXISTS interview_requests (
#             id INTEGER PRIMARY KEY AUTOINCREMENT,
#             token TEXT UNIQUE NOT NULL,
#             interviewer_name TEXT NOT NULL,
#             media_name TEXT NOT NULL,
#             topic TEXT NOT NULL,
#             method TEXT NOT NULL,
#             datetime TEXT NOT NULL,
#             meeting_link TEXT,
#             status TEXT DEFAULT 'Pending',
#             request_date TEXT NOT NULL
#         )
#         ''')
        
#         cursor.execute('''
#         CREATE TABLE IF NOT EXISTS audio_recordings (
#             id INTEGER PRIMARY KEY AUTOINCREMENT,
#             token TEXT NOT NULL,
#             interviewee TEXT NOT NULL,
#             interviewer TEXT NOT NULL,
#             date TEXT NOT NULL,
#             filename TEXT NOT NULL,
#             transcript TEXT,
#             FOREIGN KEY (token) REFERENCES interview_requests (token)
#         )
#         ''')
        
#         cursor.execute('''
#                        ALTER TABLE interview_requests ADD COLUMN whatsapp_link TEXT
#                        ''')
        
#         # Insert admin user jika belum ada dengan password yang di-hash
#         try:
#             hashed_admin_pw = generate_password_hash('password123')
#             hashed_user_pw = generate_password_hash('user123')
            
#             cursor.execute('INSERT INTO users (username, password, role) VALUES (?, ?, ?)', 
#                           ('admin', hashed_admin_pw, 'admin'))
#             cursor.execute('INSERT INTO users (username, password, role) VALUES (?, ?, ?)', 
#                           ('user1', hashed_user_pw, 'user'))
#         except sqlite3.IntegrityError:
#             pass  # User sudah ada
            
#         db.commit()


# Migrasi data
def migrate_data():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        
        # Migrasi users
        for username, data in users.items():
            try:
                cursor.execute('INSERT INTO users (username, password, role) VALUES (?, ?, ?)', 
                              (username, data['password'], data['role']))
            except sqlite3.IntegrityError:
                pass  # User sudah ada
        
        # Migrasi interview requests
        for request in interview_requests:
            cursor.execute('''
                INSERT OR IGNORE INTO interview_requests 
                (token, interviewer_name, media_name, topic, method, datetime, meeting_link, status, request_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                request['token'],
                request['interviewer_name'],
                request['media_name'],
                request['topic'],
                request['method'],
                request['datetime'],
                request.get('meeting_link', ''),
                request['status'],
                request['request_date']
            ))
        
        # Migrasi audio recordings
        for recording in audio_recordings:
            cursor.execute('''
                INSERT OR IGNORE INTO audio_recordings 
                (token, interviewee, interviewer, date, filename, transcript)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                recording['token'],
                recording['interviewee'],
                recording['interviewer'],
                recording['date'],
                recording['filename'],
                recording['transcript']
            ))
        
        db.commit()
        
# =============================================================== #
# =============================================================== #

weather_data = {
    'today': {
        'date': datetime.now().strftime('%A, %d %B %Y'),
        'condition': 'Partly Cloudy',
        'temp': '28°C',
        'humidity': '65%',
        'wind': '10 km/h',
        'outlook': 'Hari ini diperkirakan cerah berawan dengan kemungkinan hujan ringan di sore hari. Warga diimbau untuk tetap waspada terhadap perubahan cuaca.'
    },
    'tomorrow': {
        'condition': 'Rainy',
        'temp': '26°C',
        'outlook': 'Besok diperkirakan hujan dengan intensitas sedang. Warga diharapkan membawa payung atau jas hujan saat beraktivitas di luar ruangan.'
    }
}

warnings = [
    {'title': 'Peringatan Banjir', 'image': 'flood-warning.jpg', 'description': 'Waspada potensi banjir di daerah rendah'},
    {'title': 'Cuaca Ekstrem', 'image': 'storm-warning.jpg', 'description': 'Prakiraan angin kencang dan hujan lebat'},
    {'title': 'Gelombang Tinggi', 'image': 'wave-warning.jpg', 'description': 'Peringatan gelombang tinggi di pesisir'}
]

press_releases = [
    {
        'id': 1,
        'title': 'Konferensi Pers Bulanan BMKG',
        'date': '2023-06-15',
        'summary': 'BMKG mengadakan konferensi pers bulanan untuk membahas perkembangan iklim terkini.',
        'content': 'Dalam konferensi pers ini, BMKG akan memaparkan analisis kondisi cuaca dan iklim selama sebulan terakhir serta prakiraan untuk bulan depan...'
    },
    {
        'id': 2,
        'title': 'Peluncuran Sistem Peringatan Dini Baru',
        'date': '2023-05-28',
        'summary': 'BMKG meluncurkan sistem peringatan dini terbaru dengan teknologi canggih.',
        'content': 'Sistem baru ini mampu mendeteksi potensi bencana meteorologi lebih cepat dan akurat...'
    }
]

interview_requests = []
historical_data = []
audio_recordings = []

def generate_token():
    return ''.join(random.choices('ABCDEFGHJKLMNPQRSTUVWXYZ23456789', k=8))

#
# @app.context_processor
# def inject_users():
#     return dict(users=users)

@app.route('/')
def index():
    """Homepage with press releases and weather info"""
    return render_template('index.html', 
                         press_releases=press_releases[:3],
                         weather=weather_data['today'],
                         warnings=warnings)

# Press Release
@app.route('/press-release/<int:release_id>')
def press_release_detail(release_id):
    """Press release detail page"""
    release = next((r for r in press_releases if r['id'] == release_id), None)
    if not release:
        flash('Press release not found', 'danger')
        return redirect(url_for('index'))
    return render_template('press_release_detail.html', release=release)

# Request Interview
@app.route('/request-interview', methods=['GET', 'POST'])
def request_interview():
    if request.method == 'POST':
        token = generate_token()
        method = request.form.get('method')
        
        # Metode WhatsApp generate link
        whatsapp_link = ''
        if method == 'whatsapp':
            message = f"{app.config['WHATSAPP_DEFAULT_MSG']}{token}"
            whatsapp_link = f"https://wa.me/{app.config['WHATSAPP_ADMIN']}?text={message}"
        
        request_data = {
            'token': token,
            'interviewer_name': request.form.get('interviewer_name'),
            'media_name': request.form.get('media_name'),
            'topic': request.form.get('topic'),
            'method': method,
            'datetime': request.form.get('datetime'),
            'meeting_link': request.form.get('meeting_link', ''),
            'whatsapp_link': whatsapp_link,  # Simpan link WhatsApp
            'request_date': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'status': 'Pending'
        }
        
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            INSERT INTO interview_requests 
            (token, interviewer_name, media_name, topic, method, datetime, meeting_link, whatsapp_link, request_date, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            request_data['token'],
            request_data['interviewer_name'],
            request_data['media_name'],
            request_data['topic'],
            request_data['method'],
            request_data['datetime'],
            request_data['meeting_link'],
            request_data['whatsapp_link'],
            request_data['request_date'],
            request_data['status']
        ))
        db.commit()
        
        # Metode WhatsApp redirect ke chat
        if method == 'whatsapp':
            return redirect(whatsapp_link)
        
        flash(f'Permohonan wawancara berhasil! Token Anda: {token}', 'success')
        return redirect(url_for('request_interview'))
    
    return render_template('request_interview.html')

# Historical Data
@app.route('/historical-data')
def historical_data_view():
    if 'user' not in session:
        flash('Harap login terlebih dahulu', 'danger')
        return redirect(url_for('login'))
    
    # Query ke Supabase
    response = supabase.table('interview_requests').select('*').execute()
    requests = response.data
    
    return render_template('historical_data.html', historical_data=requests)

# Recorder
@app.route('/recorder', methods=['POST'])
def recorder():
    if 'audio_file' not in request.files:
        flash('No file uploaded', 'danger')
        return redirect(url_for('recorder'))
    
    file = request.files['audio_file']
    if file.filename == '':
        flash('No selected file', 'danger')
        return redirect(url_for('recorder'))
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_bytes = file.read()
        
        # Upload ke Supabase Storage
        bucket_name = "audios"
        supabase.storage().from_(bucket_name).upload(filename, file_bytes)
        
        # Simpan metadata ke tabel audio_recordings
        supabase.table('audio_recordings').insert({
            'token': request.form.get('token'),
            'interviewee': request.form.get('interviewee'),
            'interviewer': request.form.get('interviewer'),
            'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'filename': filename,
            'transcript': request.form.get('transcript', '')
        }).execute()
        
        flash('File berhasil diupload!', 'success')
    
    return redirect(url_for('recorder'))

# Generate PDF
@app.route('/generate-pdf/<int:recording_id>')
def generate_pdf(recording_id):
    if 'user' not in session:
        flash('Unauthorized access', 'danger')
        return redirect(url_for('login'))
    
    db = get_db()
    cursor = db.cursor()
    
    # Cek role user
    cursor.execute('SELECT role FROM users WHERE username = ?', (session['user'],))
    user = cursor.fetchone()
    
    if not user or user['role'] != 'admin':
        flash('Unauthorized access', 'danger')
        return redirect(url_for('index'))
    
    cursor.execute('SELECT * FROM audio_recordings WHERE id = ?', (recording_id,))
    recording = cursor.fetchone()
    
    if not recording:
        flash('Recording not found', 'danger')
        return redirect(url_for('recorder'))
    
    # Create PDF (sama seperti sebelumnya)
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    
    # Add content to PDF
    p.setFont("Helvetica-Bold", 16)
    p.drawString(100, 750, "Laporan Wawancara BMKG")
    
    p.setFont("Helvetica", 12)
    p.drawString(100, 720, f"Token: {recording['token']}")
    p.drawString(100, 700, f"Tanggal: {recording['date']}")
    p.drawString(100, 680, f"Pewawancara: {recording['interviewer']}")
    p.drawString(100, 660, f"Narasumber: {recording['interviewee']}")
    
    p.drawString(100, 620, "Transkrip Wawancara:")
    text = p.beginText(100, 600)
    text.setFont("Helvetica", 10)
    
    # Add transcript with word wrap
    for line in recording['transcript'].split('\n'):
        for part in [line[i:i+80] for i in range(0, len(line), 80)]:
            text.textLine(part)
    
    p.drawText(text)
    
    p.showPage()
    p.save()
    
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"transkrip_{recording['token']}.pdf", mimetype='application/pdf')

# Login
# Contoh: Fungsi login yang diubah
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Query ke Supabase
        response = supabase.table('users').select('*').eq('username', username).execute()
        user = response.data[0] if response.data else None
        
        if user and check_password_hash(user['password'], password):
            session['user'] = user['username']
            flash('Login berhasil!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Username atau password salah', 'danger')
    
    return render_template('login.html')

# Logout
@app.route('/logout')
def logout():
    """Logout"""
    session.pop('user', None)
    return redirect(url_for('index'))


if __name__ == "__main__":
    from waitress import serve
    with app.app_context():
        init_db()  # Database akan dibuat di sini
    serve(app, host="0.0.0.0", port=8080)
