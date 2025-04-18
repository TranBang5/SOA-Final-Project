from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import os
from prometheus_client import Counter, Histogram, start_http_server
import time
import requests

app = Flask(__name__)

# Prometheus metrics
REQUEST_COUNT = Counter('request_count', 'Total number of requests')
REQUEST_LATENCY = Histogram('request_latency_seconds', 'Request latency in seconds')

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'mysql+mysqlconnector://analytics_user:analytics_pass@analytics-db/analytics')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db = SQLAlchemy(app)

# Analytics Model
class Analytics(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    paste_id = db.Column(db.Integer, nullable=False)
    view_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())
    updated_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())

# Service URLs
VIEW_SERVICE_URL = os.getenv('VIEW_SERVICE_URL', 'http://view-service:5003')

@app.before_request
def before_request():
    request.start_time = time.time()

@app.after_request
def after_request(response):
    REQUEST_COUNT.inc()
    REQUEST_LATENCY.observe(time.time() - request.start_time)
    return response

@app.route('/analytics/<int:paste_id>', methods=['GET'])
def get_analytics(paste_id):
    try:
        # Get view data from view service
        response = requests.get(f"{VIEW_SERVICE_URL}/views/{paste_id}")
        if response.status_code != 200:
            return jsonify({'error': 'Failed to get view data'}), 500
        
        view_data = response.json()
        
        # Update analytics record
        analytics = Analytics.query.filter_by(paste_id=paste_id).first()
        if not analytics:
            analytics = Analytics(paste_id=paste_id, view_count=view_data['total_views'])
            db.session.add(analytics)
        else:
            analytics.view_count = view_data['total_views']
        db.session.commit()
        
        return jsonify({
            'paste_id': paste_id,
            'total_views': view_data['total_views'],
            'recent_views': view_data['recent_views']
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/analytics/<int:paste_id>/increment', methods=['POST'])
def increment_view_count(paste_id):
    analytics = Analytics.query.filter_by(paste_id=paste_id).first()
    if not analytics:
        analytics = Analytics(paste_id=paste_id)
        db.session.add(analytics)
    
    analytics.view_count += 1
    db.session.commit()
    
    return jsonify({
        'paste_id': analytics.paste_id,
        'view_count': analytics.view_count
    })

@app.route('/analytics', methods=['GET'])
def get_all_analytics():
    try:
        analytics = Analytics.query.all()
        return jsonify([{
            'paste_id': a.paste_id,
            'view_count': a.view_count,
            'created_at': a.created_at.isoformat() if a.created_at else None,
            'updated_at': a.updated_at.isoformat() if a.updated_at else None
        } for a in analytics]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Start Prometheus metrics server
    start_http_server(8000)
    
    # Create database tables
    with app.app_context():
        db.create_all()
    
    # Run the application
    app.run(host='0.0.0.0', port=5004) 