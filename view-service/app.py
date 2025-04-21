from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
import os
import requests
from datetime import datetime

app = Flask(__name__)

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'mysql+mysqlconnector://view_user:view_pass@view-db/view_db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

ANALYTIC_SERVICE_URL = os.getenv('ANALYTIC_SERVICE_URL', 'http://analytic-service:5003')

# Models
class Paste(db.Model):
    paste_id = db.Column(db.Integer, primary_key=True)
    short_url = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text, nullable=False)
    expires_at = db.Column(db.DateTime)
    view_count = db.Column(db.Integer, default=0)

class View(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    paste_id = db.Column(db.Integer, db.ForeignKey('paste.paste_id'), nullable=False)
    viewed_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

# Routes
@app.route('/')
def index():
    """
    Show all available non-expired pastes.
    """
    pastes = Paste.query.filter(
        (Paste.expires_at > datetime.utcnow()) | (Paste.expires_at == None)
    ).order_by(Paste.paste_id.desc()).all()
    return render_template('index.html', pastes=pastes)

@app.route('/paste/<short_url>', endpoint='view_by_short_url')
def view_by_short_url(short_url):
    """
    View a paste by its short URL:
    - Validates if it exists and is not expired
    - Logs the view in the database
    - Increments and updates view count
    """
    paste = Paste.query.filter_by(short_url=short_url).first()

    if not paste:
        return render_template('error.html', message='Paste not found'), 404

    if paste.expires_at and paste.expires_at < datetime.utcnow():
        return render_template('error.html', message='Paste has expired', expired_at=paste.expires_at), 410

    # Record this view
    view = View(paste_id=paste.paste_id)
    db.session.add(view)

    # Update view count (synchronous query)
    paste.view_count = View.query.filter_by(paste_id=paste.paste_id).count()
    db.session.commit()

    # Send to Analytic
    send_view_to_analytic(paste)

    return render_template('view.html', paste=paste)

def send_view_to_analytic(paste):
    """
    Sends paste view data to the Analytic service.
    """
    try:
        data = {
            "paste_id": paste.paste_id,
            "short_url": paste.short_url,
            "view_count": paste.view_count
        }
        response = requests.post(f"{ANALYTIC_SERVICE_URL}/api/track-view", json=data)
        if response.status_code != 200:
            print("Failed to report view to Analytic service:", response.status_code)
    except Exception as e:
        print("Error communicating with Analytic service:", e)

# -----------------------------
# API Endpoints
# -----------------------------

@app.route('/api/views/<int:paste_id>', methods=['GET'])
def get_views(paste_id):
    """
    API: Get current view count for a specific paste.
    """ 
    view_count = View.query.filter_by(paste_id=paste_id).count()
    return jsonify({'view_count': view_count})

@app.route('/api/pastes', methods=['GET'])
def get_pastes():
    """
    API: Return all non-expired pastes with view counts.
    """
    pastes = Paste.query.filter(
        (Paste.expires_at > datetime.utcnow()) | (Paste.expires_at == None)
    ).all()
    return jsonify([{
        'paste_id': paste.paste_id,
        'short_url': paste.short_url,
        'view_count': paste.view_count
    } for paste in pastes])

@app.route('/api/paste', methods=['POST'])
def receive_paste():
    try:
        data = request.get_json(force=True)
        if not data:
            raise ValueError("No JSON data provided")

        required_fields = ['paste_id', 'short_url', 'content']
        for field in required_fields:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")

        paste_id = data['paste_id']
        short_url = data['short_url']
        content = data['content']
        expires_at = data.get('expires_at')

        expires_at_dt = None
        if expires_at:
            try:
                expires_at_dt = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
            except ValueError as e:
                raise ValueError(f"Invalid expires_at format: {str(e)}")

        paste = Paste.query.filter_by(paste_id=paste_id).first()
        if paste:
            paste.short_url = short_url
            paste.content = content
            paste.expires_at = expires_at_dt
        else:
            paste = Paste(
                paste_id=paste_id,
                short_url=short_url,
                content=content,
                expires_at=expires_at_dt,
                view_count=0
            )
            db.session.add(paste)

        db.session.commit()
        return jsonify({"message": "Paste successfully received and stored"}), 200

    except Exception as e:
        print(f"❌ View Service Error: {str(e)}")
        import traceback
        print("Traceback:", traceback.format_exc())
        return jsonify({"error": str(e)}), 400


with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002, debug=True)
