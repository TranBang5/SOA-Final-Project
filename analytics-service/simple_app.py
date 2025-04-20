from flask import Flask, request, jsonify, render_template
import os
import time
from datetime import datetime

app = Flask(__name__)

# Simple in-memory storage for this test version
paste_views = {}
event_count = 0
start_time = time.time()

@app.route('/')
def index():
    """
    Dashboard homepage
    """
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

@app.route('/api/track-view', methods=['POST'])
def track_view():
    """
    API: Receives paste view data from the View service.
    """
    global event_count
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
    print("Starting Simple Analytics Service on port 5003...")
    app.run(host='0.0.0.0', port=5003, debug=True)