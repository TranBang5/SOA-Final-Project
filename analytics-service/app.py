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
    short_url = db.Column(db.String(255), nullable=False, index=True)
    view_count = db.Column(db.Integer, default=0)
    ip_address = db.Column(db.String(45), nullable=True)
    user_id = db.Column(db.String(36), nullable=True)
    session_id = db.Column(db.String(36), nullable=True)
    referrer = db.Column(db.String(255), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
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
    now = datetime.utcnow()
    today = now.date()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    
    # Get the most recent view count per paste and sum them
    today_views = db.session.query(func.max(ViewEvent.view_count)) \
        .filter(func.date(ViewEvent.timestamp) == today) \
        .group_by(ViewEvent.paste_id).all()
    today_views = sum(v[0] for v in today_views) if today_views else 0

    week_views = db.session.query(func.max(ViewEvent.view_count)) \
        .filter(ViewEvent.timestamp >= week_ago) \
        .group_by(ViewEvent.paste_id).all()
    week_views = sum(v[0] for v in week_views) if week_views else 0

    month_views = db.session.query(func.max(ViewEvent.view_count)) \
        .filter(ViewEvent.timestamp >= month_ago) \
        .group_by(ViewEvent.paste_id).all()
    month_views = sum(v[0] for v in month_views) if month_views else 0

    # Top 5 pastes by latest view count
    subquery = db.session.query(
        ViewEvent.paste_id,
        ViewEvent.short_url,
        func.max(ViewEvent.view_count).label('max_views')
    ).group_by(ViewEvent.paste_id, ViewEvent.short_url).subquery()

    top_pastes_query = db.session.query(
        ViewEvent.paste_id,
        ViewEvent.short_url,
        func.max(ViewEvent.view_count).label('view_count')
    ).group_by(ViewEvent.paste_id, ViewEvent.short_url) \
    .order_by(func.max(ViewEvent.view_count).desc()) \
    .limit(5)

    top_pastes = [{
        'paste_id': row.paste_id,
        'short_url': row.short_url,
        'view_count': row.view_count or 0
    } for row in top_pastes_query.all()]

    # System metrics dummy values for now
    ingestion_rate = 0
    error_rate = 0
    avg_latency = 0
    backfill_count = 0

    return render_template('index.html',
                           today_views=today_views,
                           week_views=week_views,
                           month_views=month_views,
                           top_pastes=top_pastes,
                           top_users=[],  # Optional: similar query can be done per user_id
                           ingestion_rate=ingestion_rate,
                           error_rate=error_rate,
                           avg_latency=avg_latency,
                           backfill_count=backfill_count)

@app.route('/dashboard')
def dashboard():
    """
    Enhanced analytics dashboard with real data from the database
    """
    # Calculate date ranges
    today = datetime.utcnow().date()
    start_of_day = datetime.combine(today, datetime.min.time())
    start_of_week = start_of_day - timedelta(days=today.weekday())
    start_of_month = datetime(today.year, today.month, 1)

    # Get view statistics
    today_views = ViewEvent.query.filter(ViewEvent.timestamp >= start_of_day).count()
    week_views = ViewEvent.query.filter(ViewEvent.timestamp >= start_of_week).count()
    month_views = ViewEvent.query.filter(ViewEvent.timestamp >= start_of_month).count()

    # Get top pastes
    top_pastes = db.session.query(
        ViewEvent.paste_id,
        ViewEvent.short_url,
        func.count(ViewEvent.id).label('view_count')
    ).group_by(
        ViewEvent.paste_id, 
        ViewEvent.short_url
    ).order_by(
        desc('view_count')
    ).limit(5).all()
    
    top_pastes_formatted = [
        {
            'paste_id': paste.paste_id,
            'short_url': paste.short_url,
            'view_count': paste.view_count
        }
        for paste in top_pastes
    ]

    # Get unique viewers by IP
    unique_viewers = db.session.query(
        ViewEvent.ip_address
    ).distinct().count()

    return render_template(
        'index.html',
        today_views=today_views,
        week_views=week_views,
        month_views=month_views,
        top_pastes=top_pastes_formatted,
        top_users=[],  # We could add this if we had user tracking
        unique_viewers=unique_viewers,
        ingestion_rate=0,  # These could be calculated with timestamps
        error_rate=0,
        avg_latency=0,
        backfill_count=0
    )

@app.route('/system')
def system_metrics():
    """
    Display system-level analytics and performance metrics.
    """
    # Provide dummy data for the template
    dummy_hourly_data = [{'hour': f'{h:02d}:00', 'count': 0, 'avg_time': 0.0} for h in range(24)]
    dummy_error_details = {'ExampleError': 0, 'AnotherError': 0}

    return render_template(
        'system_analytics.html',
        current_ingestion_rate=0,
        current_error_rate=0,
        current_avg_latency=0,
        backfill_count=0,
        hourly_events=dummy_hourly_data,
        hourly_errors=dummy_hourly_data,
        hourly_latency=dummy_hourly_data,
        error_details=dummy_error_details
    )

@app.route('/paste/<int:paste_id>')
def paste_analytics(paste_id):
    """
    Show detailed analytics for a specific paste
    """
    # Get paste information
    paste_views = ViewEvent.query.filter_by(paste_id=paste_id).count()
    
    if paste_views == 0:
        return render_template('error.html', message=f"No analytics data found for paste ID {paste_id}"), 404
    
    # Get the short URL from the first event (all events for this paste should have the same short_url)
    first_event = ViewEvent.query.filter_by(paste_id=paste_id).first()
    short_url = first_event.short_url
    
    # Calculate unique viewers
    unique_viewers = db.session.query(ViewEvent.ip_address).filter_by(
        paste_id=paste_id
    ).distinct().count()
    
    # Calculate average views per session (if session tracking is implemented)
    if unique_viewers > 0:
        avg_views_per_session = paste_views / unique_viewers
    else:
        avg_views_per_session = 0
    
    # Get daily view data for the past week
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    daily_views = []
    
    for i in range(7):
        day = seven_days_ago + timedelta(days=i)
        next_day = day + timedelta(days=1)
        
        count = ViewEvent.query.filter(
            ViewEvent.paste_id == paste_id,
            ViewEvent.timestamp >= day,
            ViewEvent.timestamp < next_day
        ).count()
        
        daily_views.append({
            'date': day.strftime('%Y-%m-%d'),
            'count': count
        })
    
    paste_data = {
        'paste_id': paste_id,
        'short_url': short_url
    }
    
    return render_template(
        'paste_analytics.html',
        paste=paste_data,
        total_views=paste_views,
        unique_viewers=unique_viewers,
        avg_views_per_session=round(avg_views_per_session, 2),
        daily_views=daily_views
    )

@app.route('/api/track-view', methods=['POST'])
def track_view():
    """
    API: Receives paste view data from the View service.
    """
    try:
        data = request.json
        print("✅ Received data from View service:", data)
        print("=== TRACK VIEW API CALLED ===")
        print(f"Remote address: {request.remote_addr}")
        print(f"Headers: {request.headers}")
        
        if not data or not all(k in data for k in ['paste_id', 'short_url', 'view_count']):
            print("Error: Missing required fields in request")
            return jsonify({"error": "Missing required fields"}), 400
        
        # Extract required fields
        paste_id = data['paste_id']
        short_url = data['short_url']
        view_count = data['view_count']
        
        print(f"Processing view for paste_id={paste_id}, short_url={short_url}, view_count={view_count}")
        
        # Extract optional fields
        ip_address = request.remote_addr
        user_id = data.get('user_id')
        session_id = data.get('session_id', str(uuid.uuid4()))  # Generate session ID if not provided
        referrer = data.get('referrer') or request.referrer
        user_agent = request.headers.get('User-Agent')
        
        # Extract metadata if available
        metadata = data.get('metadata', {})
        if metadata and isinstance(metadata, dict):
            metadata_json = json.dumps(metadata)
        else:
            metadata_json = None
        
        # Create view event
        event = ViewEvent(
            paste_id=paste_id,
            short_url=short_url,
            view_count=view_count,
            ip_address=ip_address,
            user_id=user_id,
            session_id=session_id,
            referrer=referrer,
            user_agent=user_agent,
            timestamp=datetime.utcnow(),
            metadata_json=metadata_json
        )
        
        # Add to database
        try:
            db.session.add(event)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Database error: {str(e)}")
            
            # Log the error
            error = ProcessingError(
                error_type="DatabaseError",
                error_message=str(e)
            )
            try:
                db.session.add(error)
                db.session.commit()
            except:
                db.session.rollback()
                
            return jsonify({"error": f"Database error: {str(e)}"}), 500
        
        print("View tracked successfully")
        return jsonify({
            "success": True, 
            "message": "View tracked successfully",
            "session_id": session_id
        }), 200
        
    except Exception as e:
        print(f"Server error: {str(e)}")
        
        # Log the error
        try:
            error = ProcessingError(
                error_type="ServerError",
                error_message=str(e)
            )
            db.session.add(error)
            db.session.commit()
        except:
            db.session.rollback()
            
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@app.route('/api/track-event', methods=['POST'])
def track_client_event():
    """
    API: Track custom client-side events (e.g., scrolls, time on page, or custom interactions)
    """
    try:
        data = request.json
        
        if not data or not all(k in data for k in ['paste_id', 'event_type']):
            return jsonify({"error": "Missing required fields"}), 400
        
        # Extract required fields
        paste_id = data['paste_id']
        event_type = data['event_type']
        
        # Look up the paste record to get its short_url
        paste_event = ViewEvent.query.filter_by(paste_id=paste_id).order_by(ViewEvent.timestamp.desc()).first()
        
        if not paste_event:
            return jsonify({"error": f"No record found for paste_id {paste_id}"}), 404
        
        short_url = paste_event.short_url
        
        # Extract optional fields
        ip_address = request.remote_addr
        user_id = data.get('user_id')
        session_id = data.get('session_id')
        referrer = data.get('referrer') or request.referrer
        user_agent = request.headers.get('User-Agent')
        
        # Create event metadata
        metadata = {
            'event_type': event_type,
            'event_data': data.get('event_data', {}),
            'client_timestamp': data.get('client_timestamp')
        }
        
        # Create the event record
        event = ViewEvent(
            paste_id=paste_id,
            short_url=short_url,
            view_count=0,  # Not a view, just an event
            ip_address=ip_address,
            user_id=user_id,
            session_id=session_id,
            referrer=referrer,
            user_agent=user_agent,
            timestamp=datetime.utcnow(),
            metadata_json=json.dumps(metadata)
        )
        
        # Add to database
        try:
            db.session.add(event)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Database error: {str(e)}")
            return jsonify({"error": f"Database error: {str(e)}"}), 500
        
        return jsonify({
            "success": True,
            "message": f"Event '{event_type}' tracked successfully"
        }), 200
        
    except Exception as e:
        print(f"Server error: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@app.route('/api/stats/dashboard', methods=['GET'])
def api_stats_dashboard():
    """
    API: Return all stats needed for a dashboard in a single request
    """
    # Date ranges
    today = datetime.utcnow().date()
    start_of_day = datetime.combine(today, datetime.min.time())
    start_of_week = start_of_day - timedelta(days=today.weekday())
    start_of_month = datetime(today.year, today.month, 1)
    
    # Get view statistics
    today_views = ViewEvent.query.filter(ViewEvent.timestamp >= start_of_day).count()
    week_views = ViewEvent.query.filter(ViewEvent.timestamp >= start_of_week).count()
    month_views = ViewEvent.query.filter(ViewEvent.timestamp >= start_of_month).count()
    total_views = ViewEvent.query.count()
    
    # Get unique viewers
    unique_viewers = db.session.query(ViewEvent.ip_address).distinct().count()
    
    # Get top pastes
    top_pastes = db.session.query(
        ViewEvent.paste_id,
        ViewEvent.short_url,
        func.count(ViewEvent.id).label('view_count')
    ).group_by(
        ViewEvent.paste_id, 
        ViewEvent.short_url
    ).order_by(
        desc('view_count')
    ).limit(5).all()
    
    top_pastes_result = [
        {
            'paste_id': paste.paste_id,
            'short_url': paste.short_url,
            'view_count': paste.view_count
        }
        for paste in top_pastes
    ]
    
    # Get time series data for the week
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=7)
    
    time_series = []
    current_date = start_date.date()
    while current_date <= end_date.date():
        day_start = datetime.combine(current_date, datetime.min.time())
        day_end = datetime.combine(current_date + timedelta(days=1), datetime.min.time())
        
        count = ViewEvent.query.filter(
            ViewEvent.timestamp >= day_start,
            ViewEvent.timestamp < day_end
        ).count()
        
        time_series.append({
            'date': current_date.isoformat(),
            'count': count
        })
        
        current_date += timedelta(days=1)
    
    # Get device distribution
    user_agents = db.session.query(
        ViewEvent.user_agent,
        func.count(ViewEvent.id).label('count')
    ).filter(
        ViewEvent.user_agent.isnot(None),
        ViewEvent.timestamp >= start_of_week
    ).group_by(
        ViewEvent.user_agent
    ).all()
    
    # Simple device detection
    devices = {
        'Mobile': 0,
        'Tablet': 0,
        'Desktop': 0,
        'Other': 0
    }
    
    for ua_record in user_agents:
        ua = ua_record.user_agent.lower()
        count = ua_record.count
        
        if 'mobile' in ua or 'android' in ua:
            devices['Mobile'] += count
        elif 'ipad' in ua or 'tablet' in ua:
            devices['Tablet'] += count
        elif ('windows' in ua or 'macintosh' in ua or 'linux' in ua) and 'mobile' not in ua:
            devices['Desktop'] += count
        else:
            devices['Other'] += count
    
    device_data = [
        {'name': device, 'value': count}
        for device, count in devices.items()
        if count > 0
    ]
    
    # Get session stats
    session_count = db.session.query(ViewEvent.session_id) \
        .filter(ViewEvent.session_id.isnot(None), ViewEvent.timestamp >= start_of_week) \
        .distinct().count()
    
    # Get error stats
    error_count = db.session.query(ProcessingError) \
        .filter(ProcessingError.timestamp >= start_of_week).count()
    
    return jsonify({
        'status': 'success',
        'data': {
            'stats': {
                'views': {
                    'today': today_views,
                    'week': week_views,
                    'month': month_views,
                    'total': total_views
                },
                'unique_viewers': unique_viewers,
                'sessions': session_count,
                'errors': error_count
            },
            'top_pastes': top_pastes_result,
            'time_series': time_series,
            'devices': device_data,
            'timestamp': datetime.utcnow().isoformat()
        }
    })

# Create database tables
with app.app_context():
    try:
        print("Creating database tables...")
        db.create_all()
        print("Database tables created successfully.")
    except Exception as e:
        print(f"Error during database initialization: {str(e)}")
        print("Will try again on next restart...")

# API endpoints for retrieving analytics data
@app.route('/api/stats/summary', methods=['GET'])
def api_stats_summary():
    """
    API: Return summary statistics of paste views
    """
    today = datetime.utcnow().date()
    start_of_day = datetime.combine(today, datetime.min.time())
    start_of_week = start_of_day - timedelta(days=today.weekday())
    start_of_month = datetime(today.year, today.month, 1)
    
    today_views = ViewEvent.query.filter(ViewEvent.timestamp >= start_of_day).count()
    week_views = ViewEvent.query.filter(ViewEvent.timestamp >= start_of_week).count()
    month_views = ViewEvent.query.filter(ViewEvent.timestamp >= start_of_month).count()
    total_views = ViewEvent.query.count()
    
    unique_viewers = db.session.query(ViewEvent.ip_address).distinct().count()
    
    return jsonify({
        "status": "success",
        "data": {
            "views": {
                "today": today_views,
                "week": week_views,
                "month": month_views,
                "total": total_views
            },
            "unique_viewers": unique_viewers,
            "timestamp": datetime.utcnow().isoformat()
        }
    })

@app.route('/api/stats/top_pastes', methods=['GET'])
def api_stats_top_pastes():
    """
    API: Return top viewed pastes
    """
    limit = request.args.get('limit', 10, type=int)
    
    top_pastes = db.session.query(
        ViewEvent.paste_id,
        ViewEvent.short_url,
        func.count(ViewEvent.id).label('view_count')
    ).group_by(
        ViewEvent.paste_id, 
        ViewEvent.short_url
    ).order_by(
        desc('view_count')
    ).limit(limit).all()
    
    result = [
        {
            'paste_id': paste.paste_id,
            'short_url': paste.short_url,
            'view_count': paste.view_count
        }
        for paste in top_pastes
    ]
    
    return jsonify({
        "status": "success",
        "data": {
            "top_pastes": result,
            "timestamp": datetime.utcnow().isoformat()
        }
    })

@app.route('/api/stats/paste/<int:paste_id>', methods=['GET'])
def api_stats_paste(paste_id):
    """
    API: Return detailed statistics for a specific paste
    """
    # Check if paste exists
    paste_count = ViewEvent.query.filter_by(paste_id=paste_id).count()
    if paste_count == 0:
        return jsonify({
            "status": "error",
            "message": f"No data found for paste ID {paste_id}"
        }), 404
    
    # Get basic stats
    first_view = ViewEvent.query.filter_by(paste_id=paste_id).order_by(ViewEvent.timestamp).first()
    last_view = ViewEvent.query.filter_by(paste_id=paste_id).order_by(ViewEvent.timestamp.desc()).first()
    
    # Get unique viewers
    unique_viewers = db.session.query(ViewEvent.ip_address).filter_by(
        paste_id=paste_id
    ).distinct().count()
    
    # Views per day over time
    min_date = first_view.timestamp.date()
    max_date = last_view.timestamp.date()
    current_date = min_date
    daily_views = []
    
    while current_date <= max_date:
        start_date = datetime.combine(current_date, datetime.min.time())
        end_date = datetime.combine(current_date + timedelta(days=1), datetime.min.time())
        
        day_count = ViewEvent.query.filter(
            ViewEvent.paste_id == paste_id,
            ViewEvent.timestamp >= start_date,
            ViewEvent.timestamp < end_date
        ).count()
        
        daily_views.append({
            "date": current_date.isoformat(),
            "count": day_count
        })
        
        current_date += timedelta(days=1)
    
    return jsonify({
        "status": "success",
        "data": {
            "paste_id": paste_id,
            "short_url": first_view.short_url,
            "total_views": paste_count,
            "unique_viewers": unique_viewers,
            "first_view": first_view.timestamp.isoformat(),
            "last_view": last_view.timestamp.isoformat(),
            "daily_views": daily_views,
            "timestamp": datetime.utcnow().isoformat()
        }
    })

@app.route('/api/stats/time_series', methods=['GET'])
def api_stats_time_series():
    """
    API: Return time-series data for analytics visualization
    """
    # Get parameters
    days = request.args.get('days', 7, type=int)
    interval = request.args.get('interval', 'day')  # day, hour, week
    paste_id = request.args.get('paste_id', type=int)  # Optional paste_id filter
    
    # Calculate the start date based on requested days
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    # Base query
    if paste_id:
        base_query = ViewEvent.query.filter(
            ViewEvent.paste_id == paste_id,
            ViewEvent.timestamp >= start_date,
            ViewEvent.timestamp <= end_date
        )
    else:
        base_query = ViewEvent.query.filter(
            ViewEvent.timestamp >= start_date,
            ViewEvent.timestamp <= end_date
        )
    
    # Format results based on interval
    result = []
    if interval == 'hour':
        # Group by hour
        current_time = start_date
        while current_time <= end_date:
            next_time = current_time + timedelta(hours=1)
            
            count = base_query.filter(
                ViewEvent.timestamp >= current_time,
                ViewEvent.timestamp < next_time
            ).count()
            
            result.append({
                'timestamp': current_time.isoformat(),
                'count': count
            })
            
            current_time = next_time
    elif interval == 'day':
        # Group by day
        current_date = start_date.date()
        while current_date <= end_date.date():
            day_start = datetime.combine(current_date, datetime.min.time())
            day_end = datetime.combine(current_date + timedelta(days=1), datetime.min.time())
            
            count = base_query.filter(
                ViewEvent.timestamp >= day_start,
                ViewEvent.timestamp < day_end
            ).count()
            
            result.append({
                'timestamp': current_date.isoformat(),
                'count': count
            })
            
            current_date += timedelta(days=1)
    elif interval == 'week':
        # Group by week (starting from Monday)
        current_date = start_date.date()
        # Adjust to the start of the week (Monday)
        current_date = current_date - timedelta(days=current_date.weekday())
        
        while current_date <= end_date.date():
            week_start = datetime.combine(current_date, datetime.min.time())
            week_end = datetime.combine(current_date + timedelta(days=7), datetime.min.time())
            
            count = base_query.filter(
                ViewEvent.timestamp >= week_start,
                ViewEvent.timestamp < week_end
            ).count()
            
            result.append({
                'timestamp': current_date.isoformat(),
                'count': count,
                'week_start': current_date.isoformat(),
                'week_end': (current_date + timedelta(days=6)).isoformat()
            })
            
            current_date += timedelta(days=7)
    
    return jsonify({
        'status': 'success',
        'data': {
            'interval': interval,
            'days': days,
            'paste_id': paste_id,
            'series': result
        }
    })

@app.route('/api/stats/referrers', methods=['GET'])
def api_stats_referrers():
    """
    API: Return referrer analytics data to track traffic sources
    """
    # Get parameters
    days = request.args.get('days', 30, type=int)
    paste_id = request.args.get('paste_id', type=int)  # Optional paste_id filter
    
    # Calculate date range
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    # Base query
    if paste_id:
        base_query = ViewEvent.query.filter(
            ViewEvent.paste_id == paste_id,
            ViewEvent.timestamp >= start_date
        )
    else:
        base_query = ViewEvent.query.filter(
            ViewEvent.timestamp >= start_date
        )
    
    # Get top referrers
    referrer_stats = db.session.query(
        ViewEvent.referrer,
        func.count(ViewEvent.id).label('count')
    ).filter(
        ViewEvent.referrer.isnot(None),
        ViewEvent.referrer != ''
    ).group_by(
        ViewEvent.referrer
    ).order_by(
        desc('count')
    ).limit(10)
    
    # Format results
    result = [
        {
            'referrer': ref.referrer or 'Direct',
            'count': ref.count
        }
        for ref in referrer_stats
    ]
    
    # Get total with referrer vs direct traffic
    total_with_referrer = base_query.filter(
        ViewEvent.referrer.isnot(None),
        ViewEvent.referrer != ''
    ).count()
    
    total_direct = base_query.filter(
        (ViewEvent.referrer.is_(None)) | 
        (ViewEvent.referrer == '')
    ).count()
    
    return jsonify({
        'status': 'success',
        'data': {
            'days': days,
            'paste_id': paste_id,
            'referrers': result,
            'summary': {
                'with_referrer': total_with_referrer,
                'direct': total_direct,
                'total': total_with_referrer + total_direct
            }
        }
    })

@app.route('/api/stats/sessions', methods=['GET'])
def api_stats_sessions():
    """
    API: Return session analytics data to understand user behavior
    """
    # Get parameters
    days = request.args.get('days', 7, type=int)
    paste_id = request.args.get('paste_id', type=int)  # Optional paste_id filter
    
    # Calculate date range
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    # Base query
    if paste_id:
        base_query = ViewEvent.query.filter(
            ViewEvent.paste_id == paste_id,
            ViewEvent.timestamp >= start_date
        )
    else:
        base_query = ViewEvent.query.filter(
            ViewEvent.timestamp >= start_date
        )
    
    # Get session counts and duration
    session_stats = db.session.query(
        ViewEvent.session_id,
        func.count(ViewEvent.id).label('view_count'),
        func.min(ViewEvent.timestamp).label('first_view'),
        func.max(ViewEvent.timestamp).label('last_view')
    ).filter(
        ViewEvent.session_id.isnot(None),
        ViewEvent.timestamp >= start_date
    )
    
    if paste_id:
        session_stats = session_stats.filter(ViewEvent.paste_id == paste_id)
    
    session_stats = session_stats.group_by(ViewEvent.session_id).all()
    
    # Calculate session durations and stats
    sessions = []
    total_duration = timedelta()
    
    for session in session_stats:
        duration = session.last_view - session.first_view
        duration_seconds = duration.total_seconds()
        
        sessions.append({
            'session_id': session.session_id,
            'view_count': session.view_count,
            'first_view': session.first_view.isoformat(),
            'last_view': session.last_view.isoformat(),
            'duration_seconds': duration_seconds
        })
        
        total_duration += duration
    
    # Calculate averages
    session_count = len(sessions)
    avg_views_per_session = sum(s['view_count'] for s in sessions) / session_count if session_count > 0 else 0
    avg_session_duration = (total_duration.total_seconds() / session_count) if session_count > 0 else 0
    
    # Count sessions by view count ranges
    view_count_ranges = {
        '1': 0,
        '2-5': 0,
        '6-10': 0,
        '11+': 0
    }
    
    for session in sessions:
        count = session['view_count']
        if count == 1:
            view_count_ranges['1'] += 1
        elif 2 <= count <= 5:
            view_count_ranges['2-5'] += 1
        elif 6 <= count <= 10:
            view_count_ranges['6-10'] += 1
        else:
            view_count_ranges['11+'] += 1
    
    return jsonify({
        'status': 'success',
        'data': {
            'days': days,
            'paste_id': paste_id,
            'session_count': session_count,
            'avg_views_per_session': round(avg_views_per_session, 2),
            'avg_session_duration_seconds': round(avg_session_duration, 2),
            'session_view_counts': view_count_ranges,
            'sessions': sessions[:10]  # Return just the first 10 sessions to avoid massive responses
        }
    })

@app.route('/api/stats/user-agents', methods=['GET'])
def api_stats_user_agents():
    """
    API: Return analytics about user agents (browsers, devices, etc.)
    """
    # Get parameters
    days = request.args.get('days', 30, type=int)
    paste_id = request.args.get('paste_id', type=int)  # Optional paste_id filter
    
    # Calculate date range
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    # Base query
    if paste_id:
        base_query = ViewEvent.query.filter(
            ViewEvent.paste_id == paste_id,
            ViewEvent.timestamp >= start_date
        )
    else:
        base_query = ViewEvent.query.filter(
            ViewEvent.timestamp >= start_date
        )
    
    # Get statistics on user agents
    user_agent_stats = db.session.query(
        ViewEvent.user_agent,
        func.count(ViewEvent.id).label('count')
    ).filter(
        ViewEvent.user_agent.isnot(None)
    ).group_by(
        ViewEvent.user_agent
    ).order_by(
        desc('count')
    ).limit(10).all()
    
    result = [
        {
            'user_agent': ua.user_agent,
            'count': ua.count
        }
        for ua in user_agent_stats
    ]
    
    # Simple browser detection
    browsers = {
        'Chrome': 0,
        'Firefox': 0,
        'Safari': 0,
        'Edge': 0,
        'IE': 0,
        'Opera': 0,
        'Other': 0
    }
    
    # Simple device detection
    devices = {
        'Mobile': 0,
        'Tablet': 0,
        'Desktop': 0,
        'Bot': 0,
        'Other': 0
    }
    
    # Process all user agents
    all_user_agents = db.session.query(
        ViewEvent.user_agent,
        func.count(ViewEvent.id).label('count')
    ).filter(
        ViewEvent.user_agent.isnot(None),
        ViewEvent.timestamp >= start_date
    )
    
    if paste_id:
        all_user_agents = all_user_agents.filter(ViewEvent.paste_id == paste_id)
        
    all_user_agents = all_user_agents.group_by(ViewEvent.user_agent).all()
    
    for ua_record in all_user_agents:
        ua = ua_record.user_agent.lower()
        count = ua_record.count
        
        # Browser detection
        if 'chrome' in ua and 'edge' not in ua and 'opr' not in ua:
            browsers['Chrome'] += count
        elif 'firefox' in ua:
            browsers['Firefox'] += count
        elif 'safari' in ua and 'chrome' not in ua:
            browsers['Safari'] += count
        elif 'edge' in ua:
            browsers['Edge'] += count
        elif 'msie' in ua or 'trident' in ua:
            browsers['IE'] += count
        elif 'opr' in ua or 'opera' in ua:
            browsers['Opera'] += count
        else:
            browsers['Other'] += count
            
        # Device detection
        if 'mobile' in ua or 'android' in ua:
            devices['Mobile'] += count
        elif 'ipad' in ua or 'tablet' in ua:
            devices['Tablet'] += count
        elif 'bot' in ua or 'crawl' in ua or 'spider' in ua:
            devices['Bot'] += count
        elif ('windows' in ua or 'macintosh' in ua or 'linux' in ua) and 'mobile' not in ua:
            devices['Desktop'] += count
        else:
            devices['Other'] += count
    
    # Format browser data for charts
    browser_data = [
        {'name': browser, 'value': count}
        for browser, count in browsers.items()
        if count > 0
    ]
    
    # Format device data for charts
    device_data = [
        {'name': device, 'value': count}
        for device, count in devices.items()
        if count > 0
    ]
    
    return jsonify({
        'status': 'success',
        'data': {
            'days': days,
            'paste_id': paste_id,
            'top_user_agents': result,
            'browser_stats': browser_data,
            'device_stats': device_data
        }
    })

if __name__ == '__main__':
    print("Starting Analytics Service on port 5003...")
    app.run(host='0.0.0.0', port=5003)