from flask import Flask, request, jsonify
import os
import requests
from datetime import datetime

app = Flask(__name__)

# Service URLs
PASTE_SERVICE_URL = os.getenv('PASTE_SERVICE_URL', 'http://paste-service:5002')
URL_SERVICE_URL = os.getenv('URL_SERVICE_URL', 'http://url-service:5001')

@app.route('/cleanup/check', methods=['POST'])
def check_expired_pastes():
    try:
        # Get all pastes from paste service
        response = requests.get(f"{PASTE_SERVICE_URL}/pastes")
        if response.status_code != 200:
            return jsonify({'error': 'Failed to get pastes'}), 500
        
        pastes = response.json()
        expired_pastes = []
        
        # Check for expired pastes
        for paste in pastes:
            if paste['expires_at'] and datetime.fromisoformat(paste['expires_at']) < datetime.now():
                expired_pastes.append(paste['id'])
        
        return jsonify({
            'expired_pastes': expired_pastes
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/cleanup/process', methods=['POST'])
def process_expired_pastes():
    try:
        # Get expired pastes
        response = requests.post(f"{URL_SERVICE_URL}/cleanup/check")
        if response.status_code != 200:
            return jsonify({'error': 'Failed to get expired pastes'}), 500
        
        expired_pastes = response.json()['expired_pastes']
        deleted_pastes = []
        
        # Delete expired pastes
        for paste_id in expired_pastes:
            # Delete from paste service
            paste_response = requests.delete(f"{PASTE_SERVICE_URL}/pastes/{paste_id}")
            if paste_response.status_code == 200:
                deleted_pastes.append(paste_id)
        
        return jsonify({
            'deleted_pastes': deleted_pastes
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5005) 