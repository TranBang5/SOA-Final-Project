from flask import Flask, request, jsonify
import os
import requests

app = Flask(__name__)

# Service URLs
URL_SERVICE_URL = os.getenv('URL_SERVICE_URL', 'http://url-service:5001')
PASTE_SERVICE_URL = os.getenv('PASTE_SERVICE_URL', 'http://paste-service:5002')
VIEW_SERVICE_URL = os.getenv('VIEW_SERVICE_URL', 'http://view-service:5003')
ANALYTICS_SERVICE_URL = os.getenv('ANALYTICS_SERVICE_URL', 'http://analytics-service:5004')
CLEANUP_SERVICE_URL = os.getenv('CLEANUP_SERVICE_URL', 'http://cleanup-service:5005')

def handle_service_response(response):
    if response.status_code >= 400:
        return jsonify(response.json()), response.status_code
    return response.json(), response.status_code

@app.route('/paste', methods=['POST'])
def create_paste():
    try:
        # Forward to paste service
        paste_data = request.get_json()
        paste_response = requests.post(f"{PASTE_SERVICE_URL}/pastes", json=paste_data)
        
        if paste_response.status_code != 201:
            return handle_service_response(paste_response)
        
        paste_id = paste_response.json()['id']
        
        # Create short URL
        url_response = requests.post(f"{URL_SERVICE_URL}/url", json={'paste_id': paste_id})
        if url_response.status_code != 201:
            return handle_service_response(url_response)
        
        short_url = url_response.json()['short_url']
        
        return jsonify({
            'paste_id': paste_id,
            'short_url': short_url
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/paste/<short_url>', methods=['GET'])
def get_paste_by_url(short_url):
    try:
        # Get paste_id from URL service
        url_response = requests.get(f"{URL_SERVICE_URL}/url/{short_url}")
        if url_response.status_code != 200:
            return handle_service_response(url_response)
        
        paste_id = url_response.json()['paste_id']
        
        # Get paste content
        paste_response = requests.get(f"{PASTE_SERVICE_URL}/pastes/{paste_id}")
        if paste_response.status_code != 200:
            return handle_service_response(paste_response)
        
        # Record view
        view_response = requests.get(f"{VIEW_SERVICE_URL}/view/{paste_id}")
        
        return handle_service_response(paste_response)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/paste/<int:paste_id>', methods=['GET'])
def get_paste(paste_id):
    # Forward to paste service
    response = requests.get(f"{PASTE_SERVICE_URL}/pastes/{paste_id}")
    return handle_service_response(response)

@app.route('/paste/<int:paste_id>', methods=['DELETE'])
def delete_paste(paste_id):
    # Forward to paste service
    response = requests.delete(f"{PASTE_SERVICE_URL}/pastes/{paste_id}")
    return handle_service_response(response)

@app.route('/analytics/<int:paste_id>', methods=['GET'])
def get_analytics(paste_id):
    # Forward to analytics service
    response = requests.get(f"{ANALYTICS_SERVICE_URL}/analytics/{paste_id}")
    return handle_service_response(response)

@app.route('/cleanup/check', methods=['POST'])
def check_expired_pastes():
    # Forward to cleanup service
    response = requests.post(f"{CLEANUP_SERVICE_URL}/cleanup/check")
    return handle_service_response(response)

@app.route('/cleanup/process', methods=['POST'])
def process_expired_pastes():
    # Forward to cleanup service
    response = requests.post(f"{CLEANUP_SERVICE_URL}/cleanup/process")
    return handle_service_response(response)

@app.route('/pastes', methods=['GET'])
def get_all_pastes():
    try:
        # Get all pastes from the paste service
        response = requests.get(f"{PASTE_SERVICE_URL}/pastes")
        if not response.ok:
            return jsonify({'error': 'Failed to get pastes'}), 500
        
        pastes = response.json()
        
        # Get short URLs for each paste
        for paste in pastes:
            try:
                url_response = requests.get(f"{URL_SERVICE_URL}/url/{paste['id']}")
                if url_response.ok:
                    url_data = url_response.json()
                    paste['short_url'] = url_data.get('short_url')
            except:
                paste['short_url'] = None
        
        return jsonify(pastes), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/analytics', methods=['GET'])
def get_all_analytics():
    # Forward to analytics service
    response = requests.get(f"{ANALYTICS_SERVICE_URL}/analytics")
    return handle_service_response(response)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000) 