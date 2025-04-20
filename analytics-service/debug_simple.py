from flask import Flask, request, jsonify
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
    try:
        print(f"Host IP address: {socket.gethostbyname(socket.gethostname())}")
    except:
        print("Could not determine host IP address")
    print("=" * 50)

@app.route('/')
def index():
    """
    Dashboard homepage
    """
    print("Index route was accessed!")
    try:
        # Calculate some simple metrics
        total_views = sum(paste_views.values()) if paste_views else 0
        
        # Create simple HTML instead of using templates
        html = f"""
        <html>
        <head>
            <title>Analytics Dashboard</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                h1 {{ color: #333; }}
                .metric {{ background-color: #f5f5f5; padding: 10px; margin: 10px 0; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <h1>Analytics Dashboard</h1>
            
            <div class="metric">
                <h2>Total Views: {total_views}</h2>
            </div>
            
            <div class="metric">
                <h2>Top Pastes</h2>
                <ul>
        """
        
        # Add top pastes to the HTML
        for paste_id, count in sorted(paste_views.items(), key=lambda x: x[1], reverse=True)[:5]:
            html += f"<li>Paste ID: {paste_id} - Views: {count}</li>"
        
        if not paste_views:
            html += "<li>No paste data available</li>"
        
        html += """
                </ul>
            </div>
        </body>
        </html>
        """
        
        return html
        
    except Exception as e:
        print(f"Error in index route: {e}")
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
    print(f"Starting Simplified Analytics Service on port {PORT}...")
    print(f"Try accessing: http://localhost:{PORT}/hello")
    print(f"or http://{socket.gethostbyname(socket.gethostname())}:{PORT}/hello")
    
    # Make sure we bind to all interfaces so both localhost and IP address work
    print("Binding to all interfaces (0.0.0.0)...")
    app.run(host='0.0.0.0', port=PORT, debug=True)