from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
import os
import requests
import logging
import time
import threading
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'mysql+mysqlconnector://cleanup_user:cleanup_pass@cleanup-db/cleanup_db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_POOL_SIZE'] = 10
app.config['SQLALCHEMY_MAX_OVERFLOW'] = 20

db = SQLAlchemy(app)

# Service configuration
VIEW_SERVICE_URL = os.getenv('VIEW_SERVICE_URL', 'http://view-service:5002')
ANALYTIC_SERVICE_URL = os.getenv('ANALYTIC_SERVICE_URL', 'http://analytic-service:5003')
REQUEST_TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', '5'))
CLEANUP_INTERVAL = int(os.getenv('CLEANUP_INTERVAL', '3600'))  # Default: 1 hour

# Models
class Paste(db.Model):
    paste_id = db.Column(db.Integer, primary_key=True)
    short_url = db.Column(db.String(10), nullable=False)
    content = db.Column(db.Text, nullable=False)
    expires_at = db.Column(db.DateTime)
    view_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_deleted = db.Column(db.Boolean, default=False)
    deleted_at = db.Column(db.DateTime)

    def to_dict(self):
        return {
            'paste_id': self.paste_id,
            'short_url': self.short_url,
            'view_count': self.view_count,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'is_deleted': self.is_deleted,
            'deleted_at': self.deleted_at.isoformat() if self.deleted_at else None
        }

# Cleanup function
def cleanup_expired_pastes():
    while True:
        try:
            logger.info("Starting cleanup of expired pastes")
            now = datetime.utcnow()

            expired_pastes = Paste.query.filter(
                Paste.expires_at <= now,
                Paste.is_deleted == False
            ).all()

            if expired_pastes:
                logger.info(f"Found {len(expired_pastes)} expired pastes to delete")

                for paste in expired_pastes:
                    try:
                        notify_analytic_service(paste)
                    except Exception as e:
                        logger.error(f"Failed to notify analytic service about deleted paste {paste.paste_id}: {str(e)}")
                    
                    # Hard delete the paste
                    db.session.delete(paste)

                db.session.commit()
                logger.info(f"Successfully deleted {len(expired_pastes)} expired pastes")
            else:
                logger.info("No expired pastes found")

        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
            db.session.rollback()

        logger.info(f"Cleanup completed. Next cleanup in {CLEANUP_INTERVAL} seconds")
        time.sleep(CLEANUP_INTERVAL)

def notify_analytic_service(paste):
    """
    Notifies the analytic service about a deleted paste.
    """
    try:
        data = paste.to_dict()
        response = requests.post(
            f"{ANALYTIC_SERVICE_URL}/api/paste-deleted",
            json=data,
            timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        logger.info(f"Successfully notified analytic service about deleted paste {paste.paste_id}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error communicating with Analytic service: {str(e)}")
        raise

# API Endpoints
@app.route('/api/health', methods=['GET'])
def health_check():
    """
    Health check endpoint for container orchestration.
    """
    return jsonify({"status": "healthy"}), 200

@app.route('/api/cleanup', methods=['POST'])
def manual_cleanup():
    """
    Manually trigger the cleanup process.
    """
    try:
        now = datetime.utcnow()
        expired_pastes = Paste.query.filter(
            Paste.expires_at <= now,
            Paste.is_deleted == False
        ).all()
        
        count = len(expired_pastes)
        
        for paste in expired_pastes:
            paste.is_deleted = True
            paste.deleted_at = now
            
            try:
                notify_analytic_service(paste)
            except Exception as e:
                logger.error(f"Failed to notify analytic service about deleted paste {paste.paste_id}: {str(e)}")
        
        db.session.commit()
        
        return jsonify({
            "message": f"Cleanup completed successfully",
            "deleted_count": count
        }), 200
        
    except Exception as e:
        logger.error(f"Error during manual cleanup: {str(e)}")
        db.session.rollback()
        return jsonify({"error": f"Failed to perform cleanup: {str(e)}"}), 500

@app.route('/api/sync', methods=['POST'])
def sync_pastes():
    """
    Sync pastes from the view service.
    """
    try:
        response = requests.get(
            f"{VIEW_SERVICE_URL}/api/pastes",
            timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        pastes_data = response.json()
        
        for paste_data in pastes_data:
            paste_id = paste_data['paste_id']
            paste = Paste.query.filter_by(paste_id=paste_id).first()
            
            if not paste:
                # Create new paste
                paste = Paste(
                    paste_id=paste_id,
                    short_url=paste_data['short_url'],
                    content="",  # Content not needed for cleanup service
                    expires_at=datetime.fromisoformat(paste_data['expires_at']) if paste_data.get('expires_at') else None,
                    view_count=paste_data.get('view_count', 0)
                )
                db.session.add(paste)
            else:
                # Update existing paste
                paste.short_url = paste_data['short_url']
                paste.expires_at = datetime.fromisoformat(paste_data['expires_at']) if paste_data.get('expires_at') else None
                paste.view_count = paste_data.get('view_count', 0)
        
        db.session.commit()
        return jsonify({"message": "Sync completed successfully"}), 200
        
    except Exception as e:
        logger.error(f"Error during sync: {str(e)}")
        db.session.rollback()
        return jsonify({"error": f"Failed to sync pastes: {str(e)}"}), 500

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return jsonify({"error": "Resource not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return jsonify({"error": "Internal server error"}), 500

# Initialize database and start cleanup thread
with app.app_context():
    db.create_all()
    
    # Start cleanup thread
    cleanup_thread = threading.Thread(target=cleanup_expired_pastes, daemon=True)
    cleanup_thread.start()
    logger.info("Cleanup thread started")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5004, debug=False)
