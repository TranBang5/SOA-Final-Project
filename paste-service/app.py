import uuid
from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import os
import secrets
import json
import requests
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# DB config
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'mysql+pymysql://paste_user:paste_pass@paste-db/paste_db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 100,
    'max_overflow': 50,
    'pool_timeout': 30,
    'pool_recycle': 1800,
}

db = SQLAlchemy(app)

# View service URL (set in docker-compose)
VIEW_SERVICE_URL = os.getenv("VIEW_SERVICE_URL", "http://view-service:5002")

# Models
class Paste(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(255), unique=True, nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)

# Create tables
with app.app_context():
    db.create_all()

# Utilities
def generate_url():
    return str(uuid.uuid4())[:12]

def map_expiration(minutes):
    return datetime.utcnow() + timedelta(minutes=minutes) if minutes else None

def send_to_view_service(paste):
    try:
        expires_at_value = paste.expires_at.isoformat() if paste.expires_at else None
        paste_data = {
            "paste_id": int(paste.id),
            "short_url": str(paste.url),
            "content": str(paste.content),
            "expires_at": expires_at_value
        }
        app.logger.info(f"Sending paste to view service: {paste_data}")
        response = requests.post(f"{VIEW_SERVICE_URL}/api/paste", json=paste_data, timeout=5)
        if response.status_code != 200:
            app.logger.error(f"View Service Error: {response.status_code}, Response: {response.text}")
            raise Exception(f"Failed to send paste to view service: {response.status_code}")
        app.logger.info(f"Successfully sent paste to view service: {paste.url}")
    except Exception as e:
        app.logger.error(f"Error sending to view service: {e}")
        raise


# Routes
@app.route("/")
def home():
    return render_template("create.html")

@app.route("/pastes/", methods=["POST"])
def create_paste():
    try:
        data = request.json
        content = data.get("content")
        expires_in = data.get("expires_in")
        if not content:
            return jsonify({"error": "Content is required"}), 400
        url = generate_url()
        while Paste.query.filter_by(url=url).first():
            url = generate_url()
        paste = Paste(content=content, url=url, expires_at=map_expiration(expires_in))
        db.session.add(paste)
        db.session.commit()
        send_to_view_service(paste)
        return jsonify({
            "id": paste.id,
            "url": paste.url,
            "created_at": paste.created_at,
            "expires_at": paste.expires_at
        }), 201
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Failed to create paste: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

@app.route("/pastes/<int:paste_id>", methods=["GET"])
def get_paste_by_id(paste_id):
    paste = Paste.query.get(paste_id)
    if not paste:
        return jsonify({"error": "Paste not found"}), 404
    return jsonify({
        "id": paste.id,
        "url": paste.url,
        "content": paste.content,
        "created_at": paste.created_at,
        "expires_at": paste.expires_at
    })

@app.route("/pastes/by-url/<string:url>", methods=["GET"])
def get_paste_by_url(url):
    paste = Paste.query.filter_by(url=url).first()
    if not paste:
        return jsonify({"error": "Paste not found"}), 404
    return jsonify({
        "id": paste.id,
        "url": paste.url,
        "content": paste.content,
        "created_at": paste.created_at,
        "expires_at": paste.expires_at
    })

@app.route("/api/pastes/expired", methods=["GET"])
def get_expired_pastes():
    try:
        expired_pastes = Paste.query.filter(
            Paste.expires_at <= datetime.utcnow(),
            Paste.expires_at != None
        ).all()
        pastes_data = [
            {
                "paste_id": paste.id,
                "short_url": paste.url,
                "expires_at": paste.expires_at.isoformat() if paste.expires_at else None
            }
            for paste in expired_pastes
        ]
        app.logger.info(f"Retrieved {len(pastes_data)} expired pastes from Paste Service")
        return jsonify({"status": "success", "data": pastes_data}), 200
    except Exception as e:
        app.logger.error(f"Failed to retrieve expired pastes: {str(e)}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500

@app.route("/api/paste/<int:paste_id>", methods=["DELETE"])
def delete_paste(paste_id):
    try:
        paste = Paste.query.get(paste_id)
        if not paste:
            app.logger.warning(f"Attempted to delete non-existent paste {paste_id}")
            return jsonify({"error": "Paste not found"}), 404
        
        db.session.delete(paste)
        db.session.commit()
        app.logger.info(f"Successfully deleted paste {paste_id} from Paste Service")
        return jsonify({"message": "Paste deleted successfully"}), 200
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Failed to delete paste {paste_id}: {str(e)}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
