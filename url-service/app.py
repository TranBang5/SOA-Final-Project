from flask import Flask, request, jsonify
import os
import mysql.connector
import string
import random
import logging

app = Flask(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database configuration
db_config = {
    'host': os.getenv('MYSQL_HOST', 'url-db'),
    'user': os.getenv('MYSQL_USER', 'root'),
    'password': os.getenv('MYSQL_PASSWORD', 'root'),
    'database': os.getenv('MYSQL_DATABASE', 'url_service')
}

def get_db_connection():
    return mysql.connector.connect(**db_config)

def generate_short_url():
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(6))

@app.route('/url', methods=['POST'])
def create_url():
    try:
        data = request.get_json()
        paste_id = data.get('paste_id')
        
        logger.info(f"Received request to create URL for paste_id: {paste_id}")
        
        if not paste_id:
            logger.warning("Missing paste_id in request")
            return jsonify({'error': 'paste_id is required'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Generate a unique short URL
        while True:
            short_url = generate_short_url()
            cursor.execute("SELECT id FROM urls WHERE short_url = %s", (short_url,))
            if not cursor.fetchone():
                break
        
        cursor.execute(
            "INSERT INTO urls (paste_id, short_url) VALUES (%s, %s)",
            (paste_id, short_url)
        )
        conn.commit()
        
        cursor.close()
        conn.close()
        
        logger.info(f"Successfully created short URL: {short_url} for paste_id: {paste_id}")
        return jsonify({
            'short_url': short_url,
            'paste_id': paste_id
        }), 201
        
    except Exception as e:
        logger.error(f"Error creating URL: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/url/<short_url>', methods=['GET'])
def get_url(short_url):
    try:
        logger.info(f"Received request to get URL for short_url: {short_url}")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT paste_id FROM urls WHERE short_url = %s",
            (short_url,)
        )
        result = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        if not result:
            logger.warning(f"URL not found for short_url: {short_url}")
            return jsonify({'error': 'URL not found'}), 404
        
        logger.info(f"Successfully retrieved paste_id: {result[0]} for short_url: {short_url}")
        return jsonify({
            'paste_id': result[0],
            'short_url': short_url
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting URL: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    logger.info("Starting URL Service...")
    app.run(host='0.0.0.0', port=5001) 