from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
import os
import time
from datetime import datetime, timedelta
import uuid
from sqlalchemy import func, desc
import threading
import queue
import mysql.connector
import sys
import json

app = Flask(__name__)

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'mysql+mysqlconnector://analytics_user:analytics_pass@analytics-db/analytics_db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Wait for database to be ready
def wait_for_db(max_retries=30, retry_interval=2):
    """Wait for database to be ready"""
    retries = 0
    while retries < max_retries:
        try:
            # Try to connect to the database
            conn_parts = app.config['SQLALCHEMY_DATABASE_URI'].replace('mysql+mysqlconnector://', '').split('/')
            conn_uri = conn_parts[0]
            user_pass, host = conn_uri.split('@')
            user, password = user_pass.split(':')
            
            print(f"Attempt {retries+1}/{max_retries} to connect to database")
            conn = mysql.connector.connect(
                host=host,
                user=user,
                password=password
            )
            conn.close()
            print("Database connection successful!")
            return True
        except Exception as e:
            print(f"Database connection failed: {str(e)}")
            retries += 1
            print(f"Retrying in {retry_interval} seconds...")
            time.sleep(retry_interval)
    
    print("Max retries reached. Could not connect to database.")
    return False

# Wait for database to be ready before proceeding
if not wait_for_db():
    print("Could not connect to database. Exiting...")
    sys.exit(1)

db = SQLAlchemy(app)

# Models
class ViewEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    paste_id = db.Column(db.Integer, nullable=False, index=True)
    short_url = db.Column(db.String(10), nullable=False, index=True)
    view_count = db.Column(db.Integer, default=0)
    ip_address = db.Column(db.String(45), nullable=True)
    user_id = db.Column(db.String(36), nullable=True)
    session_id = db.Column(db.String(36), nullable=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    processed = db.Column(db.Boolean, default=False)
    processing_time = db.Column(db.Float, nullable=True)
    metadata_json = db.Column(db.Text, nullable=True)

class ProcessingError(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    error_type = db.Column(db.String(50), nullable=False)
    error_message = db.Column(db.String(255), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

# Routes
@app.route('/')
def index():
    """
    Dashboard homepage
    """
    return render_template('index.html', 
                          today_views=0, 
                          week_views=0, 
                          month_views=0,
                          top_pastes=[],
                          top_users=[],
                          ingestion_rate=0,
                          error_rate=0,
                          avg_latency=0,
                          backfill_count=0)

@app.route('/api/track-view', methods=['POST'])
def track_view():
    """
    API: Receives paste view data from the View service.
    """
    try:
        data = request.json
        
        if not data or not all(k in data for k in ['paste_id', 'short_url', 'view_count']):
            return jsonify({"error": "Missing required fields"}), 400
        
        # Extract required fields
        paste_id = data['paste_id']
        short_url = data['short_url']
        view_count = data['view_count']
        
        # Extract optional fields
        ip_address = request.remote_addr
        
        # Create view event
        event = ViewEvent(
            paste_id=paste_id,
            short_url=short_url,
            view_count=view_count,
            ip_address=ip_address,
            timestamp=datetime.utcnow()
        )
        
        # Add to database
        try:
            db.session.add(event)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return jsonify({"error": f"Database error: {str(e)}"}), 500
        
        return jsonify({"success": True, "message": "View tracked successfully"}), 200
        
    except Exception as e:
        return jsonify({"error": f"Server error: {str(e)}"}), 500

# Create database tables
with app.app_context():
    try:
        print("Creating database tables...")
        db.create_all()
        print("Database tables created successfully.")
    except Exception as e:
        print(f"Error during database initialization: {str(e)}")
        print("Will try again on next restart...")

if __name__ == '__main__':
    print("Starting Analytics Service on port 5003...")
    app.run(host='0.0.0.0', port=5003)