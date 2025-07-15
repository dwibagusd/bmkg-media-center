# app.py
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
def make_app():
    # Import inside factory
    from datetime import datetime
    import os, io, random
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    from werkzeug.security import generate_password_hash, check_password_hash
    from supabase import create_client, Client

    # -------- App config --------
    app = Flask(__name__)
    app.secret_key = os.environ.get('FLASK_SECRET', 'supersecretkey')
    app.config['UPLOAD_FOLDER'] = 'static/uploads'
    app.config['ALLOWED_EXTENSIONS'] = {'wav', 'mp3', 'ogg'}
    app.config['WHATSAPP_ADMIN'] = '6281932689046'
    app.config['WHATSAPP_DEFAULT_MSG'] = 'Halo BMKG, saya ingin konfirmasi permohonan wawancara dengan token: '

    # Ensure upload folder exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # Initialize Supabase client
    SUPABASE_URL = os.environ['SUPABASE_URL']
    SUPABASE_KEY = os.environ['SUPABASE_KEY']
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Utility
    def allowed_file(filename):
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

    def generate_token():
        return ''.join(random.choices('ABCDEFGHJKLMNPQRSTUVWXYZ23456789', k=8))

    # ------- Routes -------
    @app.route('/')
    def index():
        # Static press_releases, weather_data defined below
        return render_template('index.html', press_releases=press_releases[:3], weather=weather_data['today'], warnings=warnings)

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
            method = request.form['method']
            # Build record
            record = {
                'token': token,
                'interviewer_name': request.form['interviewer_name'],
                'media_name': request.form['media_name'],
                'topic': request.form['topic'],
                'method': method,
                'datetime': request.form['datetime'],
                'meeting_link': request.form.get('meeting_link', ''),
                'whatsapp_link': '',
                'request_date': datetime.now().isoformat(sep=' '),
                'status': 'Pending'
            }
            if method == 'whatsapp':
                msg = f"{app.config['WHATSAPP_DEFAULT_MSG']}{token}"
                record['whatsapp_link'] = f"https://wa.me/{app.config['WHATSAPP_ADMIN']}?text={msg}"
            # Insert into Supabase
            supabase.table('interview_requests').insert(record).execute()
            if method == 'whatsapp':
                return redirect(record['whatsapp_link'])
            flash(f"Permohonan wawancara berhasil! Token Anda: {token}", 'success')
            return redirect(url_for('request_interview'))
        return render_template('request_interview.html')

    @app.route('/historical-data')
    def historical_data_view():
        if 'user' not in session:
            flash('Harap login terlebih dahulu', 'danger')
            return redirect(url_for('login'))
        resp = supabase.table('interview_requests').select('*').execute()
        return render_template('historical_data.html', historical_data=resp.data)

    @app.route('/recorder', methods=['GET', 'POST'])
    def recorder():
        if request.method == 'POST':
            file = request.files.get('audio_file')
            if not file or file.filename == '':
                flash('No file selected', 'danger')
                return redirect(url_for('recorder'))
            if allowed_file(file.filename):
                filename = secure_filename(file.filename)
                data = file.read()
                supabase.storage().from_('audios').upload(filename, data)
                supabase.table('audio_recordings').insert({
                    'token': request.form['token'],
                    'interviewee': request.form['interviewee'],
                    'interviewer': request.form['interviewer'],
                    'date': datetime.now().isoformat(sep=' '),
                    'filename': filename,
                    'transcript': request.form.get('transcript','')
                }).execute()
                flash('File berhasil diupload!', 'success')
            return redirect(url_for('recorder'))
        return render_template('recorder.html')

    @app.route('/generate-pdf/<int:recording_id>')
    def generate_pdf(recording_id):
        if 'user' not in session:
            flash('Unauthorized access', 'danger')
            return redirect(url_for('login'))
        # Check role
        user_resp = supabase.table('users').select('role').eq('username', session['user']).single().execute()
        if user_resp.data['role'] != 'admin':
            flash('Unauthorized access', 'danger')
            return redirect(url_for('index'))
        rec = supabase.table('audio_recordings').select('*').eq('id', recording_id).single().execute().data
        if not rec:
            flash('Recording not found', 'danger')
            return redirect(url_for('recorder'))
        # Create PDF
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        p.setFont("Helvetica-Bold", 16)
        p.drawString(100, 750, "Laporan Wawancara BMKG")
        p.setFont("Helvetica", 12)
        p.drawString(100,720, f"Token: {rec['token']}")
        p.drawString(100,700, f"Tanggal: {rec['date']}")
        p.drawString(100,680, f"Pewawancara: {rec['interviewer']}")
        p.drawString(100,660, f"Narasumber: {rec['interviewee']}")
        p.drawString(100,620, "Transkrip Wawancara:")
        text = p.beginText(100,600)
        text.setFont("Helvetica", 10)
        for line in rec['transcript'].splitlines():
            for chunk in [line[i:i+80] for i in range(0, len(line), 80)]:
                text.textLine(chunk)
        p.drawText(text)
        p.showPage()
        p.save()
        buffer.seek(0)
        return send_file(buffer, as_attachment=True, download_name=f"transkrip_{rec['token']}.pdf",
                         mimetype='application/pdf')

    @app.route('/login', methods=['GET','POST'])
    def login():
        if request.method == 'POST':
            username = request.form['username']
            password = request.form['password']
            resp = supabase.table('users').select('*').eq('username', username).single().execute()
            user = resp.data
            if user and check_password_hash(user['password'], password):
                session['user'] = user['username']
                flash('Login berhasil!', 'success')
                return redirect(url_for('index'))
            flash('Username atau password salah', 'danger')
        return render_template('login.html')

    @app.route('/logout')
    def logout():
        session.pop('user', None)
        return redirect(url_for('index'))

    return app


if __name__ == '__main__':
    from waitress import serve
    app = make_app()
    serve(app, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
