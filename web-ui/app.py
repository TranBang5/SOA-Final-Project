from flask import Flask, render_template, request, jsonify
import os
import requests

app = Flask(__name__)

# Service URLs
API_GATEWAY_URL = os.getenv('API_GATEWAY_URL', 'http://api-gateway:5000')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/paste')
def new_paste():
    return render_template('paste.html')

@app.route('/analytics')
def analytics():
    return render_template('analytics.html')

@app.route('/paste/<short_url>')
def view_paste(short_url):
    return render_template('view.html', short_url=short_url)

@app.route('/api/paste', methods=['POST'])
def create_paste():
    try:
        response = requests.post(f"{API_GATEWAY_URL}/paste", json=request.get_json())
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/paste/<short_url>', methods=['GET'])
def get_paste(short_url):
    try:
        response = requests.get(f"{API_GATEWAY_URL}/paste/{short_url}")
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/analytics/<int:paste_id>', methods=['GET'])
def get_analytics(paste_id):
    try:
        response = requests.get(f"{API_GATEWAY_URL}/analytics/{paste_id}")
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/pastes', methods=['GET'])
def get_all_pastes():
    try:
        # Get all pastes from the API gateway
        response = requests.get(f"{API_GATEWAY_URL}/pastes")
        if not response.ok:
            return jsonify({'error': 'Failed to get pastes'}), 500
        
        pastes = response.json()
        
        # Get analytics for each paste
        for paste in pastes:
            try:
                analytics_response = requests.get(f"{API_GATEWAY_URL}/analytics/{paste['paste_id']}")
                if analytics_response.ok:
                    analytics_data = analytics_response.json()
                    paste['view_count'] = analytics_data.get('total_views', 0)
                    paste['last_viewed'] = analytics_data.get('recent_views', [None])[0]
            except:
                paste['view_count'] = 0
                paste['last_viewed'] = None
        
        return jsonify(pastes), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/analytics', methods=['GET'])
def get_all_analytics():
    try:
        response = requests.get(f"{API_GATEWAY_URL}/analytics")
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5006) 