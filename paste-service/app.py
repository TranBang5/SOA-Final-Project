import os
import uuid
import logging
import redis
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
from flask import Flask, jsonify, request, render_template
import requests
from celery import Celery

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Constants
VIEW_SERVICE_URL = os.getenv('VIEW_SERVICE_URL', 'http://view-haproxy:80')
REQUEST_TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', '2'))
REDIS_HOST = os.getenv('REDIS_HOST', 'redis')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
RETRY_ATTEMPTS = int(os.getenv('RETRY_ATTEMPTS', '3'))
RETRY_DELAY = float(os.getenv('RETRY_DELAY', '1'))
BASE62_CHARS = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'

# Initialize Redis client with connection pool
redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    decode_responses=True,
    db=0,
    max_connections=1000,
    socket_timeout=1,
    socket_connect_timeout=1
)

# Initialize Celery
celery_app = Celery(
    'paste_service',
    broker=f'redis://{REDIS_HOST}:{REDIS_PORT}/0',
    backend=f'redis://{REDIS_HOST}:{REDIS_PORT}/1',
    task_queues={
        'view_service': {'exchange': 'view_service', 'routing_key': 'view_service'}
    }
)
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30,
    task_soft_time_limit=25,
    broker_connection_retry_on_startup=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1
)

# Helper functions
def base62_encode(num):
    """Encode a number to base62."""
    if not isinstance(num, int) or num < 0:
        logger.error(f"Invalid input for base62_encode: {num}")
        raise ValueError("Input must be a non-negative integer")
    if num == 0:
        return BASE62_CHARS[0]
    chars = []
    while num:
        chars.append(BASE62_CHARS[num % 62])
        num //= 62
    return ''.join(chars[::-1])

def generate_short_url(length=8):
    """Generate a short URL from UUID, encoded in base62, and ensure uniqueness using Redis."""
    try:
        max_attempts = 5
        for _ in range(max_attempts):
            uuid_int = uuid.uuid4().int & ((1 << 64) - 1)
            short_url = base62_encode(uuid_int)
            if len(short_url) < length:
                short_url = base62_encode(uuid_int + len(BASE62_CHARS))[:length]
            short_url = short_url[:length].ljust(length, BASE62_CHARS[0])
            
            if not redis_client.sismember("used_short_urls", short_url):
                redis_client.sadd("used_short_urls", short_url)
                logger.info(f"Generated unique short_url: {short_url}")
                return short_url
                
        logger.error("Failed to generate unique short_url after max attempts")
        raise ValueError("Could not generate unique short_url")
    except Exception as e:
        logger.error(f"Failed to generate short_url: {str(e)}")
        raise

@celery_app.task(queue='view_service', bind=True, max_retries=RETRY_ATTEMPTS, default_retry_delay=RETRY_DELAY * 1000)  # Delay in ms
def send_paste_to_view_service_async(self, paste_data):
    try:
        response = requests.post(
            f"{VIEW_SERVICE_URL}/api/paste",
            json=paste_data,
            timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        logger.info(f"Successfully sent paste {paste_data['paste_id']} to View Service")
    except Exception as e:
        logger.error(f"Failed to send paste to View Service: {str(e)}")
        raise self.retry(exc=e)

def generate_paste_id():
    """Generate paste_id using Redis counter."""
    try:
        paste_id = redis_client.incr("paste_id_counter")
        logger.info(f"Generated paste_id: {paste_id}")
        return paste_id
    except redis.RedisError as e:
        logger.error(f"Failed to generate paste_id from Redis: {str(e)}")
        raise

# Routes
@app.route('/pastes/', methods=['POST'])
def create_paste():
    short_url = None
    try:
        data = request.get_json()
        content = data.get('content')
        expires_in = data.get('expires_in', None)

        if not content:
            return jsonify({"error": "Content is required"}), 400

        paste_id = generate_paste_id()
        short_url = generate_short_url(length=8)
        created_at = datetime.utcnow()
        expires_at = None
        if expires_in:
            try:
                expires_at = created_at + timedelta(seconds=int(expires_in))
            except ValueError:
                redis_client.srem("used_short_urls", short_url)
                return jsonify({"error": "Invalid expires_in value"}), 400

        paste_data = {
            "paste_id": paste_id,
            "short_url": short_url,
            "content": content,
            "expires_at": expires_at.isoformat() if expires_at else None,
            "view_count": 0
        }

        # Cache the paste in Redis
        cache_key = f"paste:{short_url}"
        try:
            redis_client.setex(
                name=cache_key,
                time=int(expires_in) if expires_in else 7200,
                value=json.dumps(paste_data)
            )
            logger.info(f"Cached paste {paste_id} with short_url {short_url} in Redis")
        except redis.RedisError as e:
            logger.error(f"Failed to cache paste {paste_id}: {str(e)}")

        # Queue paste to View Service asynchronously
        try:
            send_paste_to_view_service_async.delay(paste_data)
        except Exception as e:
            redis_client.srem("used_short_urls", short_url)
            logger.error(f"Failed to queue paste to View Service: {str(e)}")
            return jsonify({"error": "Failed to queue paste for processing"}), 500

        return jsonify({
            "status": "success",
            "data": {
                "paste_id": paste_id,
                "short_url": short_url,
                "url": f"{request.host_url}paste/{short_url}"
            }
        }), 201

    except Exception as e:
        if short_url:
            redis_client.srem("used_short_urls", short_url)
        logger.error(f"Failed to create paste: {str(e)}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500

@app.route("/")
def home():
    return render_template("create.html")

@app.route("/health", methods=["GET"])
def health():
    try:
        redis_client.ping()
        return jsonify({"status": "ok"}), 200
    except redis.RedisError as e:
        logger.error(f"Health check failed: {str(e)}")
        return jsonify({"status": "unhealthy", "error": str(e)}), 503

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
