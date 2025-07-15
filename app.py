# Import Library
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from datetime import datetime, timedelta
import os
import random
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import io
from supabase import create_client, Client
import logging

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'supersecretkey')
app.config['UPLOAD_FOLDER'] = 'static/uploads/'
app.config['ALLOWED_EXTENSIONS'] = {'wav', 'mp3', 'ogg'}
app.config['WHATSAPP_ADMIN'] = '6281932689046'  # Nomor WhatsApp admin dengan kode negara
app.config['WHATSAPP_DEFAULT_MSG'] = 'Halo BMKG, saya ingin konfirmasi permohonan wawancara dengan token: '

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Buat folder unggahan
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

from supabase import create_client
import os

# Load variabel dari environment
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# Inisialisasi Supabase
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# =============================================================== #
# Data dummy (diganti dengan query database di implementasi nyata)
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

def generate_token():
    return ''.join(random.choices('ABCDEFGHJKLMNPQRSTUVWXYZ23456789', k=8))

@app.route('/')
def index():
    """Homepage with press releases and weather info"""
    return render_template('index.html', 
                         press_releases=press_releases[:3],
                         weather=weather_data['today'],
                         warnings=warnings)

@app.route('/press-release/<int:release_id>')
def press_release_detail(release_id):
    """Press release detail page"""
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
            'whatsapp_link': whatsapp_link,
            'status': 'Pending',
            'request_date': datetime.now().strftime('%Y-%m-%d %H:%M')
        }
        
        try:
            # Simpan ke Supabase
            response = supabase.table('interview_requests').insert(request_data).execute()
            if hasattr(response, 'error') and response.error:
                logger.error(f"Supabase insert error: {response.error}")
                flash('Gagal menyimpan permintaan wawancara', 'danger')
            else:
                # Metode WhatsApp redirect ke chat
                if method == 'whatsapp':
                    return redirect(whatsapp_link)
                
                flash(f'Permohonan wawancara berhasil! Token Anda: {token}', 'success')
                return redirect(url_for('request_interview'))
                
        except Exception as e:
            logger.exception("Error saving interview request")
            flash('Terjadi kesalahan server: ' + str(e), 'danger')
    
    return render_template('request_interview.html')

@app.route('/historical-data')
def historical_data_view():
    if 'user' not in session:
        flash('Harap login terlebih dahulu', 'danger')
        return redirect(url_for('login'))
    
    try:
        # Query ke Supabase
        response = supabase.table('interview_requests').select('*').execute()
        if hasattr(response, 'error') and response.error:
            logger.error(f"Supabase query error: {response.error}")
            flash('Gagal mengambil data', 'danger')
            requests = []
        else:
            requests = response.data
    except Exception as e:
        logger.exception("Error fetching historical data")
        flash('Terjadi kesalahan server', 'danger')
        requests = []
    
    return render_template('historical_data.html', historical_data=requests)

@app.route('/recorder', methods=['GET', 'POST'])
def recorder():
    if request.method == 'GET':
        return render_template('recorder.html')
    
    if 'audio_file' not in request.files:
        flash('Tidak ada file yang diunggah', 'danger')
        return redirect(url_for('recorder'))
    
    file = request.files['audio_file']
    if file.filename == '':
        flash('Tidak ada file dipilih', 'danger')
        return redirect(url_for('recorder'))
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        try:
            # Upload ke Supabase Storage
            bucket_name = "audios"
            with open(file_path, 'rb') as f:
                file_content = f.read()
            
            # Upload file
            res = supabase.storage.from_(bucket_name).upload(
                file_path, 
                file_content,
                file_options={"content-type": file.content_type}
            )
            
            if 'error' in res and res['error']:
                logger.error(f"Supabase upload error: {res['error']}")
                flash('Gagal mengunggah file ke server', 'danger')
            else:
                # Simpan metadata ke database
                recording_data = {
                    'token': request.form.get('token'),
                    'interviewee': request.form.get('interviewee'),
                    'interviewer': request.form.get('interviewer'),
                    'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
                    'filename': filename,
                    'transcript': request.form.get('transcript', '')
                }
                
                db_res = supabase.table('audio_recordings').insert(recording_data).execute()
                if hasattr(db_res, 'error') and db_res.error:
                    logger.error(f"Supabase insert error: {db_res.error}")
                    flash('Gagal menyimpan metadata rekaman', 'warning')
                else:
                    flash('Rekaman berhasil disimpan!', 'success')
                
                # Hapus file lokal setelah diupload
                os.remove(file_path)
                
        except Exception as e:
            logger.exception("Error in recorder")
            flash('Terjadi kesalahan server: ' + str(e), 'danger')
    
    return redirect(url_for('recorder'))

@app.route('/generate-pdf/<recording_id>')
def generate_pdf(recording_id):
    if 'user' not in session:
        flash('Akses ditolak', 'danger')
        return redirect(url_for('login'))
    
    try:
        # Cek role user
        user_res = supabase.table('users').select('role').eq('username', session['user']).execute()
        if hasattr(user_res, 'error') and user_res.error:
            flash('Gagal memverifikasi pengguna', 'danger')
            return redirect(url_for('index'))
            
        user = user_res.data[0] if user_res.data else None
        if not user or user.get('role') != 'admin':
            flash('Akses terbatas untuk admin', 'danger')
            return redirect(url_for('index'))
        
        # Ambil data rekaman
        recording_res = supabase.table('audio_recordings').select('*').eq('id', recording_id).execute()
        if hasattr(recording_res, 'error') and recording_res.error:
            flash('Rekaman tidak ditemukan', 'danger')
            return redirect(url_for('recorder'))
            
        recording = recording_res.data[0] if recording_res.data else None
        if not recording:
            flash('Rekaman tidak ditemukan', 'danger')
            return redirect(url_for('recorder'))
        
        # Create PDF
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
        transcript = recording.get('transcript', '')
        if transcript:
            for line in transcript.split('\n'):
                for part in [line[i:i+80] for i in range(0, len(line), 80)]:
                    text.textLine(part)
        
        p.drawText(text)
        p.showPage()
        p.save()
        
        buffer.seek(0)
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f"transkrip_{recording['token']}.pdf",
            mimetype='application/pdf'
        )
        
    except Exception as e:
        logger.exception("Error generating PDF")
        flash('Terjadi kesalahan saat membuat PDF', 'danger')
        return redirect(url_for('recorder'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        try:
            # Query ke Supabase
            response = supabase.table('users').select('*').eq('username', username).execute()
            if hasattr(response, 'error') and response.error:
                flash('Database error', 'danger')
                return redirect(url_for('login'))
                
            user = response.data[0] if response.data else None
            
            if user and check_password_hash(user['password'], password):
                session['user'] = user['username']
                flash('Login berhasil!', 'success')
                return redirect(url_for('index'))
            else:
                flash('Username atau password salah', 'danger')
                
        except Exception as e:
            logger.exception("Login error")
            flash('Terjadi kesalahan server', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logout"""
    session.pop('user', None)
    return redirect(url_for('index'))

@app.before_request
def log_request():
    app.logger.info(f"Incoming request: {request.method} {request.path}")

@app.after_request
def log_response(response):
    app.logger.info(f"Response: {response.status}")
    return response

@app.route('/test')
def test():
    return {
        "status": "OK",
        "supabase_configured": bool(os.getenv('SUPABASE_URL')),
        "env_keys": list(os.environ.keys())
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)   
    print("SUPABASE_URL:", SUPABASE_URL)
    print("SUPABASE_KEY:", SUPABASE_KEY)
