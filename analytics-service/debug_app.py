from flask import Flask, request, jsonify, render_template
import os
import time
from datetime import datetime
import socket

app = Flask(__name__)

# Simple in-memory storage for this test version
paste_views = {}
event_count = 0
start_time = time.time()

# Print helpful diagnostic information
def print_diagnostic_info():
    print("=" * 50)
    print("DIAGNOSTICS INFORMATION")
    print("=" * 50)
    print(f"Current directory: {os.getcwd()}")
    print(f"Template folder exists: {os.path.exists('templates')}")
    print(f"Host IP address: {socket.gethostbyname(socket.gethostname())}")
    print(f"Flask app instance: {app}")
    print("=" * 50)

@app.route('/')
def index():
    """
    Dashboard homepage
    """
    print("Index route was accessed!")
    try:
        # Calculate some simple metrics
        now = datetime.utcnow()
        total_views = sum(paste_views.values()) if paste_views else 0
        
        # Format the top pastes data
        top_pastes = [
            {
                'paste_id': paste_id, 
                'short_url': f'url_{paste_id}', 
                'view_count': count
            } 
            for paste_id, count in sorted(paste_views.items(), key=lambda x: x[1], reverse=True)[:5]
        ]
        
        # Calculate ingestion rate
        time_elapsed = time.time() - start_time
        ingestion_rate = event_count / time_elapsed if time_elapsed > 0 else 0
        
        print("Rendering index template...")
        return render_template(
            'index.html',
            today_views=total_views,
            week_views=total_views,
            month_views=total_views,
            top_pastes=top_pastes,
            top_users=[],
            ingestion_rate=round(ingestion_rate, 2),
            error_rate=0,
            avg_latency=0,
            backfill_count=0
        )
    except Exception as e:
        print(f"Error rendering index: {e}")
        return f"Error: {str(e)}", 500

@app.route('/hello')
def hello():
    """
    Simple test route
    """
    return "Hello from Analytics Service! If you see this, the server is working."

@app.route('/api/track-view', methods=['POST'])
def track_view():
    """
    API: Receives paste view data from the View service.
    """
    global event_count
    print("Track view endpoint was accessed!")
    try:
        data = request.json
        print(f"Received data: {data}")
        
        if not data or not all(k in data for k in ['paste_id', 'short_url', 'view_count']):
            return jsonify({"error": "Missing required fields"}), 400
        
        # Extract required fields
        paste_id = data['paste_id']
        short_url = data['short_url']
        view_count = data['view_count']
        
        # Store the data (simple in-memory storage)
        paste_views[paste_id] = paste_views.get(paste_id, 0) + 1
        event_count += 1
        
        print(f"Current paste views: {paste_views}")
        
        return jsonify({"success": True, "message": "View tracked successfully"}), 200
        
    except Exception as e:
        print(f"Error tracking view: {e}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

if __name__ == '__main__':
    # Use a different port (8080) in case 5003 is blocked
    PORT = 8080
    print_diagnostic_info()
    print(f"Starting Debug Analytics Service on port {PORT}...")
    print(f"Try accessing: http://localhost:{PORT}/hello")
    print(f"or http://{socket.gethostbyname(socket.gethostname())}:{PORT}/hello")
    app.run(host='0.0.0.0', port=PORT, debug=True)