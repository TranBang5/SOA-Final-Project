from flask import Flask, request, jsonify
import os
import json
from datetime import datetime, timedelta

app = Flask(__name__)

# In-memory storage for pastes
pastes = {}

@app.route('/pastes', methods=['POST'])
def create_paste():
    try:
        data = request.get_json()
        content = data.get('content')
        expiration = data.get('expiration')
        visibility = data.get('visibility', 'public')
        
        if not content:
            return jsonify({'error': 'Content is required'}), 400
        
        # Generate paste ID
        paste_id = len(pastes) + 1
        
        # Calculate expiration time
        if expiration:
            expires_at = datetime.now() + timedelta(minutes=int(expiration))
        else:
            expires_at = None
        
        # Store paste
        pastes[paste_id] = {
            'id': paste_id,
            'content': content,
            'created_at': datetime.now().isoformat(),
            'expires_at': expires_at.isoformat() if expires_at else None,
            'visibility': visibility
        }
        
        return jsonify(pastes[paste_id]), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/pastes/<int:paste_id>', methods=['GET'])
def get_paste(paste_id):
    try:
        if paste_id not in pastes:
            return jsonify({'error': 'Paste not found'}), 404
        
        paste = pastes[paste_id]
        
        # Check if paste has expired
        if paste['expires_at'] and datetime.fromisoformat(paste['expires_at']) < datetime.now():
            return jsonify({'error': 'Paste has expired'}), 410
        
        return jsonify(paste), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/pastes/<int:paste_id>', methods=['DELETE'])
def delete_paste(paste_id):
    try:
        if paste_id not in pastes:
            return jsonify({'error': 'Paste not found'}), 404
        
        del pastes[paste_id]
        return jsonify({'message': 'Paste deleted'}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/pastes', methods=['GET'])
def get_all_pastes():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("SELECT * FROM pastes ORDER BY created_at DESC")
        pastes = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify(pastes), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002) 