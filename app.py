from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///helpdesk.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Konfigurasi folder upload
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)

class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nrp = db.Column(db.String(50), nullable=True)
    phone_number = db.Column(db.String(50), nullable=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='To Do')
    attachment = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Ticket {self.id}>'

class TicketHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('ticket.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False)
    changed_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    ticket = db.relationship('Ticket', backref=db.backref('history', lazy=True, order_by='TicketHistory.changed_at.desc()'))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
    # Buat tabel jika belum ada
    db.create_all()
    
    # Create default admin user if not exists
    if not User.query.filter_by(username='admin').first():
        hashed_pw = generate_password_hash('admin123')
        admin = User(username='admin', password=hashed_pw)
        db.session.add(admin)
        db.session.commit()

@app.route('/')
def public_index():
    return render_template('public.html')

@app.route('/create', methods=['POST'])
def create():
    nrp = request.form.get('nrp')
    phone_number = request.form.get('phone_number')
    title = request.form.get('title')
    description = request.form.get('description')
    attachment_file = request.files.get('attachment')
    
    filename = None
    if attachment_file and attachment_file.filename:
        filename = secure_filename(attachment_file.filename)
        filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
        attachment_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    
    if title and description:
        new_ticket = Ticket(
            nrp=nrp, 
            phone_number=phone_number,
            title=title, 
            description=description, 
            attachment=filename
        )
        db.session.add(new_ticket)
        db.session.commit()
        
        # Tambah riwayat status
        history = TicketHistory(ticket_id=new_ticket.id, status='To Do')
        db.session.add(history)
        db.session.commit()
        
        flash(f'Tiket berhasil diajukan! Nomor Tiket Anda: TKT-{new_ticket.id}. Harap simpan nomor ini untuk melacak status.', 'success')
        
    return redirect(url_for('public_index'))

@app.route('/track', methods=['GET'])
def track():
    ticket_id_query = request.args.get('ticket_id', '')
    ticket = None
    error = None
    
    if ticket_id_query:
        try:
            num = int(ticket_id_query.upper().replace('TKT-', '').strip())
            ticket = Ticket.query.get(num)
            if not ticket:
                error = 'Tiket tidak ditemukan.'
        except ValueError:
            error = 'Format nomor tiket tidak valid. Contoh yang benar: TKT-1'
            
    return render_template('track.html', ticket=ticket, error=error, query=ticket_id_query)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Username atau password salah.', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    tickets = Ticket.query.order_by(Ticket.created_at.desc()).all()
    board = {
        'To Do': [],
        'In Progress': [],
        'Review': [],
        'Done': []
    }
    for ticket in tickets:
        if ticket.status in board:
            board[ticket.status].append(ticket)
        else:
            board['To Do'].append(ticket)
            
    return render_template('index.html', board=board)

@app.route('/update_ajax/<int:id>', methods=['POST'])
@login_required
def update_ajax(id):
    ticket = Ticket.query.get_or_404(id)
    data = request.get_json()
    new_status = data.get('status')
    
    if new_status in ['To Do', 'In Progress', 'Review', 'Done'] and ticket.status != new_status:
        ticket.status = new_status
        history = TicketHistory(ticket_id=ticket.id, status=new_status)
        db.session.add(history)
        db.session.commit()
        return {'success': True}
    return {'success': False}, 400

@app.route('/update/<int:id>', methods=['POST'])
@login_required
def update(id):
    ticket = Ticket.query.get_or_404(id)
    new_status = request.form.get('status')
    
    if new_status in ['To Do', 'In Progress', 'Review', 'Done'] and ticket.status != new_status:
        ticket.status = new_status
        history = TicketHistory(ticket_id=ticket.id, status=new_status)
        db.session.add(history)
        db.session.commit()
        
    return redirect(url_for('dashboard'))

@app.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete(id):
    ticket = Ticket.query.get_or_404(id)
    db.session.delete(ticket)
    db.session.commit()
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
