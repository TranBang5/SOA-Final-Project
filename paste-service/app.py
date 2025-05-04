import os
import uuid
import logging
import redis
from datetime import datetime, timedelta
from dotenv import load_dotenv
from flask import Flask, jsonify, request, render_template
import requests
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

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
REQUEST_TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', '5'))
REDIS_HOST = os.getenv('REDIS_HOST', 'redis')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
RETRY_ATTEMPTS = int(os.getenv('RETRY_ATTEMPTS', '3'))
RETRY_DELAY = float(os.getenv('RETRY_DELAY', '1'))
BASE62_CHARS = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'

# Initialize Redis client
redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    decode_responses=True,
    db=0
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
    """Generate a short URL from UUID, encoded in base62."""
    try:
        # Generate UUID4 and take the first 64 bits (8 bytes)
        uuid_int = uuid.uuid4().int & ((1 << 64) - 1)  # Mask to 64 bits
        # Encode to base62
        short_url = base62_encode(uuid_int)
        # Pad with additional encoding if too short
        if len(short_url) < length:
            short_url = base62_encode(uuid_int + len(BASE62_CHARS))[:length]
        # Ensure length is exactly 'length'
        short_url = short_url[:length].ljust(length, BASE62_CHARS[0])
        if len(short_url) != length:
            logger.error(f"Generated short_url has incorrect length: {short_url}")
            raise ValueError("Failed to generate valid short_url")
        logger.info(f"Generated short_url: {short_url}")
        return short_url
    except Exception as e:
        logger.error(f"Failed to generate short_url: {str(e)}")
        raise

@retry(
    stop=stop_after_attempt(RETRY_ATTEMPTS),
    wait=wait_fixed(RETRY_DELAY),
    retry=retry_if_exception_type((requests.RequestException, requests.HTTPError)),
    reraise=True
)
def send_paste_to_view_service(paste_data):
    try:
        response = requests.post(
            f"{VIEW_SERVICE_URL}/api/paste",
            json=paste_data,
            timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        logger.info(f"Successfully sent paste {paste_data['paste_id']} to View Service")
        return response.json()
    except Exception as e:
        logger.error(f"Failed to send paste to View Service: {str(e)}")
        raise

@retry(
    stop=stop_after_attempt(RETRY_ATTEMPTS),
    wait=wait_fixed(RETRY_DELAY),
    retry=retry_if_exception_type((requests.RequestException, requests.HTTPError)),
    reraise=True
)

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
    try:
        data = request.get_json()
        content = data.get('content')
        expires_in = data.get('expires_in', None)

        if not content:
            return jsonify({"error": "Content is required"}), 400

        paste_id = generate_paste_id()  
        while True:
            short_url = generate_short_url(length=8)
            try:
                response = requests.get(f"{VIEW_SERVICE_URL}/api/paste/{short_url}", timeout=REQUEST_TIMEOUT)
                if response.status_code == 404:
                    break 
            except requests.RequestException:
                break 
        created_at = datetime.utcnow()
        expires_at = None
        if expires_in:
            try:
                expires_at = created_at + timedelta(seconds=int(expires_in))
            except ValueError:
                return jsonify({"error": "Invalid expires_in value"}), 400

        paste_data = {
            "paste_id": paste_id,
            "short_url": short_url,
            "content": content,
            "expires_at": expires_at.isoformat() if expires_at else None
        }

        # Send paste to View Service
        send_paste_to_view_service(paste_data)

        return jsonify({
            "status": "success",
            "data": {
                "paste_id": paste_id,
                "short_url": short_url,
                "url": f"{request.host_url}paste/{short_url}"
            }
        }), 201

    except Exception as e:
        logger.error(f"Failed to create paste: {str(e)}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500

@app.route("/")
def home():
    return render_template("create.html")

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
