from functools import wraps
import time
import redis
from celery import Celery
import json
from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
import os
import requests
from datetime import datetime
from sqlalchemy import func
from sqlalchemy.exc import OperationalError

app = Flask(__name__)

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'mysql+mysqlconnector://view_user:view_pass@view-db/view_db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 100,
    'max_overflow': 50,
    'pool_timeout': 10,
    'pool_recycle': 300,
    'pool_pre_ping': True
}

# Initialize database with retry
def init_db_with_retry(max_retries=5, delay=5):
    retries = 0
    while retries < max_retries:
        try:
            db.init_app(app)
            with app.app_context():
                db.create_all()
            return
        except OperationalError as e:
            app.logger.error(f"Failed to initialize database (attempt {retries + 1}): {e}")
            if retries < max_retries - 1:
                time.sleep(delay)
                retries += 1
            else:
                raise Exception(f"Failed to initialize database after {max_retries} attempts: {e}")

db = SQLAlchemy()
init_db_with_retry()

ANALYTIC_SERVICE_URL = os.getenv('ANALYTIC_SERVICE_URL', 'http://analytics-service:5003')

redis_client = redis.Redis(host='redis', port=6379, decode_responses=True, db=0)

def retry_on_deadlock(max_retries=3, delay=0.1):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except OperationalError as e:
                    if "Deadlock found" in str(e) and attempt < max_retries - 1:
                        app.logger.warning(f"Deadlock detected, retrying ({attempt + 1}/{max_retries})...")
                        time.sleep(delay * (2 ** attempt))
                        db.session.rollback()
                        continue
                    raise
        return wrapper
    return decorator

# Models
class Paste(db.Model):
    paste_id = db.Column(db.Integer, primary_key=True)
    short_url = db.Column(db.String(255), nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    expires_at = db.Column(db.DateTime, index=True)
    view_count = db.Column(db.Integer, default=0)

class View(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    paste_id = db.Column(db.Integer, db.ForeignKey('paste.paste_id'), nullable=False, index=True)
    viewed_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

# Health check endpoint
@app.route('/health', methods=['GET'])
def health():
    try:
        db.session.execute('SELECT 1').fetchall()
        redis_client.ping()
        return jsonify({"status": "healthy"}), 200
    except (OperationalError, redis.RedisError) as e:
        app.logger.error(f"Health check failed: {str(e)}")
        return jsonify({"status": "unhealthy", "error": str(e)}), 503

# Routes
@app.route('/')
def index():
    cache_key = "index:pastes"
    cached = redis_client.get(cache_key)
    if cached:
        pastes = [Paste(**paste_data) for paste_data in json.loads(cached)]
        return render_template('index.html', pastes=pastes)

    try:
        pastes = db.session.query(Paste).filter(
            (Paste.expires_at > datetime.utcnow()) | (Paste.expires_at == None)
        ).order_by(Paste.paste_id.desc()).limit(50).all()
        paste_data = [{
            'paste_id': p.paste_id,
            'short_url': p.short_url,
            'content': p.content,
            'expires_at': p.expires_at.isoformat() if p.expires_at else None,
            'view_count': p.view_count
        } for p in pastes]
        redis_client.setex(cache_key, 60, json.dumps(paste_data))
        return render_template('index.html', pastes=pastes)
    except OperationalError as e:
        app.logger.error(f"Database connection error in index: {str(e)}")
        return render_template('error.html', message='Database unavailable'), 503

@app.route('/paste/<short_url>', endpoint='view_by_short_url')
@retry_on_deadlock(max_retries=3, delay=0.1)
def view_by_short_url(short_url):
    try:
        cache_key = f"paste:{short_url}"
        count_key = f"view_count:{short_url}"
        
        pipe = redis_client.pipeline()
        pipe.get(cache_key)
        pipe.incr(count_key)
        cached_paste, new_count = pipe.execute()

        paste = None
        if cached_paste:
            paste_data = json.loads(cached_paste)
            paste = Paste(
                paste_id=paste_data['paste_id'],
                short_url=paste_data['short_url'],
                content=paste_data['content'],
                expires_at=datetime.fromisoformat(paste_data['expires_at']) if paste_data['expires_at'] else None,
                view_count=new_count
            )
        else:
            try:
                paste = db.session.query(Paste).filter_by(short_url=short_url).first()
                if not paste:
                    return render_template('error.html', message='Paste not found'), 404
                paste.view_count = new_count
                paste_data = {
                    'paste_id': paste.paste_id,
                    'short_url': paste.short_url,
                    'content': paste.content,
                    'expires_at': paste.expires_at.isoformat() if paste.expires_at else None,
                    'view_count': paste.view_count
                }
                redis_client.setex(cache_key, 7200, json.dumps(paste_data))
            except OperationalError as e:
                app.logger.error(f"Database connection error in view_by_short_url: {str(e)}")
                if not cached_paste:
                    return render_template('error.html', message='Database unavailable'), 503

        if paste.expires_at and paste.expires_at < datetime.utcnow():
            redis_client.setex(cache_key, 60, json.dumps({"expired": True}))
            return render_template('error.html', message='Paste has expired', expired_at=paste.expires_at), 410

        send_view_to_analytic(paste)
        return render_template('view.html', paste=paste)
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error in view_by_short_url: {str(e)}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

celery_app = Celery('tasks', broker='redis://redis:6379/0', task_queues={
    'analytic': {'exchange': 'analytic', 'routing_key': 'analytic'}
})

@celery_app.task(queue='analytic')
def send_view_to_analytic_async(paste_data):
    try:
        response = requests.post(f"{ANALYTIC_SERVICE_URL}/api/track-view", json=paste_data, timeout=2)
        if response.status_code != 200:
            app.logger.error(f"Failed to report view: {response.status_code}")
    except Exception as e:
        app.logger.error(f"Error sending to Analytic service: {e}")

@celery_app.task
def sync_view_counts():
    try:
        keys = redis_client.keys("view_count:*")
        for key in keys:
            short_url = key.split(":")[1]
            count = int(redis_client.get(key) or 0)
            with app.app_context():
                try:
                    paste = db.session.query(Paste).filter_by(short_url=short_url).first()
                    if paste:
                        db.session.query(Paste).filter(Paste.paste_id == paste.paste_id).update(
                            {Paste.view_count: count},
                            synchronize_session=False
                        )
                        db.session.commit()
                        cache_key = f"paste:{short_url}"
                        cached_paste = redis_client.get(cache_key)
                        if cached_paste:
                            paste_data = json.loads(cached_paste)
                            paste_data['view_count'] = count
                            redis_client.setex(cache_key, 86400, json.dumps(paste_data))
                except OperationalError as e:
                    app.logger.error(f"Database connection error in sync_view_counts: {str(e)}")
                    continue
            redis_client.delete(key)
    except Exception as e:
        app.logger.error(f"Error syncing view counts: {str(e)}")

def send_view_to_analytic(paste):
    paste_data = {
        "paste_id": paste.paste_id,
        "short_url": paste.short_url,
        "view_count": paste.view_count
    }
    send_view_to_analytic_async.delay(paste_data)

# API Endpoints
@app.route('/api/views/<int:paste_id>', methods=['GET'])
def get_views(paste_id):
    count_key = f"view_count:{paste_id}"
    view_count = redis_client.get(count_key) or 0
    return jsonify({'view_count': int(view_count)})

@app.route('/paste/<short_url>', methods=['GET'], endpoint='get_paste')
def get_paste(short_url):
    cache_key = f"paste:{short_url}"
    cached = redis_client.get(cache_key)
    if cached:
        return jsonify(json.loads(cached)), 200

    try:
        paste = db.session.query(Paste).filter_by(short_url=short_url).first()
        if not paste:
            return jsonify({"error": "Paste not found"}), 404
        response = {
            "paste_id": paste.paste_id,
            "short_url": paste.short_url,
            "content": paste.content,
            "expires_at": paste.expires_at.isoformat() if paste.expires_at else None,
            "view_count": paste.view_count
        }
        redis_client.setex(cache_key, 3600, json.dumps(response))
        return jsonify(response), 200
    except OperationalError as e:
        app.logger.error(f"Database connection error in get_paste: {str(e)}")
        return jsonify({"error": "Database unavailable"}), 503

@app.route('/api/paste', methods=['POST'])
@retry_on_deadlock(max_retries=3, delay=0.1)
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

        cache_key = f"paste:{short_url}"
        paste_data = {
            'paste_id': paste.paste_id,
            'short_url': paste.short_url,
            'content': paste.content,
            'expires_at': paste.expires_at.isoformat() if paste.expires_at else None,
            'view_count': paste.view_count
        }
        redis_client.setex(cache_key, 3600, json.dumps(paste_data))

        return jsonify({"message": "Paste successfully received and stored"}), 200
    except OperationalError as e:
        app.logger.error(f"Database connection error in receive_paste: {str(e)}")
        return jsonify({"error": "Database unavailable"}), 503
    except Exception as e:
        app.logger.error(f"View Service Error: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 400

@app.route("/api/pastes/expired", methods=["GET"])
@retry_on_deadlock(max_retries=3, delay=0.1)
def get_expired_pastes():
    try:
        expired_pastes = Paste.query.filter(
            Paste.expires_at <= datetime.utcnow(),
            Paste.expires_at != None
        ).all()
        pastes_data = [
            {
                "paste_id": paste.paste_id,
                "short_url": paste.short_url,
                "expires_at": paste.expires_at.isoformat() if paste.expires_at else None
            }
            for paste in expired_pastes
        ]
        app.logger.info(f"Retrieved {len(pastes_data)} expired pastes from View Service")
        return jsonify({"status": "success", "data": pastes_data}), 200
    except OperationalError as e:
        app.logger.error(f"Database error retrieving expired pastes: {str(e)}")
        return jsonify({"error": "Database unavailable"}), 503
    except Exception as e:
        app.logger.error(f"Failed to retrieve expired pastes: {str(e)}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500
    
@app.route("/api/paste/<int:paste_id>", methods=["DELETE"])
@retry_on_deadlock(max_retries=3, delay=0.1)
def delete_paste(paste_id):
    try:
        paste = Paste.query.filter_by(paste_id=paste_id).first()
        if not paste:
            app.logger.warning(f"Attempted to delete non-existent paste {paste_id}")
            return jsonify({"error": "Paste not found"}), 404
        
        # Xóa paste khỏi database
        db.session.delete(paste)
        db.session.commit()
        
        # Xóa cache liên quan trong Redis
        cache_key = f"paste:{paste.short_url}"
        count_key = f"view_count:{paste.short_url}"
        redis_client.delete(cache_key, count_key)
        
        app.logger.info(f"Successfully deleted paste {paste_id} and related cache from View Service")
        return jsonify({"message": "Paste deleted successfully"}), 200
    except OperationalError as e:
        db.session.rollback()
        app.logger.error(f"Database error deleting paste {paste_id}: {str(e)}")
        return jsonify({"error": "Database unavailable"}), 503
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Failed to delete paste {paste_id}: {str(e)}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002, debug=False)
