from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
import os
import time
from datetime import datetime, timedelta
import uuid
from sqlalchemy import func, desc, extract, cast, Interval
from sqlalchemy.dialects.mysql import JSON
import threading
import queue

app = Flask(__name__)

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'mysql+mysqlconnector://analytics_user:analytics_pass@analytics-db/analytics_db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Event processing queue and metrics
event_queue = queue.Queue()
processing_times = []
error_count = {
    'parsing': 0,
    'processing': 0,
    'database': 0
}
event_count = 0
event_start_time = time.time()
backfill_count = 0

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
    metadata = db.Column(JSON, nullable=True)

class ProcessingError(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    error_type = db.Column(db.String(50), nullable=False)
    error_message = db.Column(db.String(255), nullable=False)
    raw_data = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

class AnalyticsAggregate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    paste_id = db.Column(db.Integer, nullable=False, index=True)
    total_views = db.Column(db.Integer, default=0)
    unique_viewers = db.Column(db.Integer, default=0)
    avg_views_per_session = db.Column(db.Float, default=0.0)
    last_updated = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

class SystemMetrics(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    metric_name = db.Column(db.String(50), nullable=False, index=True)
    metric_value = db.Column(db.Float, default=0.0)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

# Routes
@app.route('/')
def index():
    """
    Dashboard homepage showing system-wide analytics
    """
    # Get total system views by time period (today, this week, this month)
    now = datetime.utcnow()
    today_start = datetime(now.year, now.month, now.day)
    
    today_views = ViewEvent.query.filter(ViewEvent.timestamp >= today_start).count()
    
    week_start = now - timedelta(days=now.weekday())
    week_views = ViewEvent.query.filter(ViewEvent.timestamp >= week_start).count()
    
    month_start = datetime(now.year, now.month, 1)
    month_views = ViewEvent.query.filter(ViewEvent.timestamp >= month_start).count()
    
    # Get top 5 most viewed pastes
    top_pastes = db.session.query(
        ViewEvent.paste_id, 
        ViewEvent.short_url,
        func.count(ViewEvent.id).label('view_count')
    ).group_by(ViewEvent.paste_id, ViewEvent.short_url).order_by(desc('view_count')).limit(5).all()
    
    # Get top 5 users with most paste views
    top_users = db.session.query(
        ViewEvent.user_id, 
        func.count(ViewEvent.id).label('view_count')
    ).filter(ViewEvent.user_id != None).group_by(ViewEvent.user_id).order_by(desc('view_count')).limit(5).all()
    
    # Get event ingestion rate (events/sec)
    global event_count, event_start_time
    time_elapsed = time.time() - event_start_time
    ingestion_rate = event_count / time_elapsed if time_elapsed > 0 else 0
    
    # Get error rates
    total_errors = sum(error_count.values())
    total_events = event_count
    error_rate = (total_errors / total_events) * 100 if total_events > 0 else 0
    
    # Get average processing latency
    avg_latency = sum(processing_times) / len(processing_times) if processing_times else 0
    
    return render_template(
        'index.html',
        today_views=today_views,
        week_views=week_views, 
        month_views=month_views,
        top_pastes=top_pastes,
        top_users=top_users,
        ingestion_rate=round(ingestion_rate, 2),
        error_rate=round(error_rate, 2),
        avg_latency=round(avg_latency * 1000, 2),  # convert to ms
        backfill_count=backfill_count
    )

@app.route('/paste/<paste_id>')
def paste_analytics(paste_id):
    """
    View analytics for a specific paste
    """
    # Basic paste info
    paste = ViewEvent.query.filter_by(paste_id=paste_id).order_by(ViewEvent.timestamp.desc()).first()
    
    if not paste:
        return render_template('error.html', message='Paste analytics not found'), 404
    
    # Total views
    total_views = ViewEvent.query.filter_by(paste_id=paste_id).count()
    
    # Unique viewers (by IP)
    unique_ips = db.session.query(func.count(func.distinct(ViewEvent.ip_address))).filter(
        ViewEvent.paste_id == paste_id,
        ViewEvent.ip_address != None
    ).scalar()
    
    # Unique viewers (by user_id)
    unique_users = db.session.query(func.count(func.distinct(ViewEvent.user_id))).filter(
        ViewEvent.paste_id == paste_id,
        ViewEvent.user_id != None
    ).scalar()
    
    # Unique viewers (total - combine IP and user_id)
    unique_viewers = unique_ips + unique_users
    
    # Average views per session
    session_views = db.session.query(
        ViewEvent.session_id,
        func.count(ViewEvent.id).label('views')
    ).filter(
        ViewEvent.paste_id == paste_id,
        ViewEvent.session_id != None
    ).group_by(ViewEvent.session_id).all()
    
    avg_views_per_session = sum(s.views for s in session_views) / len(session_views) if session_views else 0
    
    # Views over time (last 7 days by day)
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    daily_views = db.session.query(
        func.date(ViewEvent.timestamp).label('date'),
        func.count(ViewEvent.id).label('count')
    ).filter(
        ViewEvent.paste_id == paste_id,
        ViewEvent.timestamp >= seven_days_ago
    ).group_by(func.date(ViewEvent.timestamp)).order_by('date').all()
    
    return render_template(
        'paste_analytics.html',
        paste=paste,
        total_views=total_views,
        unique_viewers=unique_viewers,
        avg_views_per_session=round(avg_views_per_session, 2),
        daily_views=daily_views
    )

@app.route('/system')
def system_analytics():
    """
    View system-wide analytics and metrics
    """
    # Event ingestion rate over time (last 24 hours by hour)
    day_ago = datetime.utcnow() - timedelta(days=1)
    hourly_events = db.session.query(
        func.date_format(ViewEvent.timestamp, '%Y-%m-%d %H:00:00').label('hour'),
        func.count(ViewEvent.id).label('count')
    ).filter(ViewEvent.timestamp >= day_ago).group_by('hour').order_by('hour').all()
    
    # Error rates over time (last 24 hours by hour)
    hourly_errors = db.session.query(
        func.date_format(ProcessingError.timestamp, '%Y-%m-%d %H:00:00').label('hour'),
        func.count(ProcessingError.id).label('count')
    ).filter(ProcessingError.timestamp >= day_ago).group_by('hour').order_by('hour').all()
    
    # Processing latency over time
    hourly_latency = db.session.query(
        func.date_format(ViewEvent.timestamp, '%Y-%m-%d %H:00:00').label('hour'),
        func.avg(ViewEvent.processing_time).label('avg_time')
    ).filter(
        ViewEvent.timestamp >= day_ago,
        ViewEvent.processing_time != None
    ).group_by('hour').order_by('hour').all()
    
    # Current metrics
    global event_count, event_start_time, processing_times, error_count
    time_elapsed = time.time() - event_start_time
    ingestion_rate = event_count / time_elapsed if time_elapsed > 0 else 0
    
    total_errors = sum(error_count.values())
    error_rate = (total_errors / event_count) * 100 if event_count > 0 else 0
    avg_latency = sum(processing_times) / len(processing_times) if processing_times else 0
    
    return render_template(
        'system_analytics.html',
        hourly_events=hourly_events,
        hourly_errors=hourly_errors, 
        hourly_latency=hourly_latency,
        current_ingestion_rate=round(ingestion_rate, 2),
        current_error_rate=round(error_rate, 2),
        current_avg_latency=round(avg_latency * 1000, 2),  # convert to ms
        backfill_count=backfill_count,
        error_details=error_count
    )

# API Endpoints
@app.route('/api/track-view', methods=['POST'])
def track_view():
    """
    API: Receives paste view data from the View service.
    """
    global event_count
    
    try:
        start_time = time.time()
        data = request.json
        
        if not data or not all(k in data for k in ['paste_id', 'short_url', 'view_count']):
            error_count['parsing'] += 1
            error = ProcessingError(
                error_type='parsing',
                error_message='Missing required fields',
                raw_data=str(request.data)
            )
            db.session.add(error)
            db.session.commit()
            return jsonify({"error": "Missing required fields"}), 400
        
        # Extract required fields
        paste_id = data['paste_id']
        short_url = data['short_url']
        view_count = data['view_count']
        
        # Extract optional fields
        ip_address = request.remote_addr
        user_id = data.get('user_id')
        session_id = data.get('session_id') or str(uuid.uuid4())  # Generate a session ID if not provided
        
        # Create view event
        event = ViewEvent(
            paste_id=paste_id,
            short_url=short_url,
            view_count=view_count,
            ip_address=ip_address,
            user_id=user_id,
            session_id=session_id,
            timestamp=datetime.utcnow(),
            metadata=data.get('metadata')
        )
        
        # Add to database
        try:
            db.session.add(event)
            db.session.commit()
        except Exception as e:
            error_count['database'] += 1
            db.session.rollback()
            error = ProcessingError(
                error_type='database',
                error_message=str(e),
                raw_data=str(data)
            )
            db.session.add(error)
            db.session.commit()
            return jsonify({"error": "Database error"}), 500
        
        # Put in queue for processing
        event_queue.put(event.id)
        
        # Update metrics
        event_count += 1
        processing_time = time.time() - start_time
        processing_times.append(processing_time)
        
        # Keep only last 1000 processing times to avoid memory issues
        if len(processing_times) > 1000:
            processing_times.pop(0)
        
        return jsonify({"success": True, "message": "View tracked successfully"}), 200
        
    except Exception as e:
        error_count['processing'] += 1
        try:
            error = ProcessingError(
                error_type='processing',
                error_message=str(e),
                raw_data=str(request.data)
            )
            db.session.add(error)
            db.session.commit()
        except:
            pass
        
        return jsonify({"error": "Server error"}), 500

@app.route('/api/paste/<paste_id>/analytics', methods=['GET'])
def get_paste_analytics(paste_id):
    """
    API: Get analytics data for a specific paste
    """
    try:
        paste_id = int(paste_id)
    except ValueError:
        return jsonify({"error": "Invalid paste ID"}), 400
    
    # Get aggregated analytics
    aggregate = AnalyticsAggregate.query.filter_by(paste_id=paste_id).first()
    
    if aggregate:
        return jsonify({
            "paste_id": paste_id,
            "total_views": aggregate.total_views,
            "unique_viewers": aggregate.unique_viewers,
            "avg_views_per_session": aggregate.avg_views_per_session,
            "last_updated": aggregate.last_updated.isoformat()
        }), 200
    else:
        # If no pre-aggregated data, calculate on the fly
        total_views = ViewEvent.query.filter_by(paste_id=paste_id).count()
        
        unique_ips = db.session.query(func.count(func.distinct(ViewEvent.ip_address))).filter(
            ViewEvent.paste_id == paste_id,
            ViewEvent.ip_address != None
        ).scalar() or 0
        
        unique_users = db.session.query(func.count(func.distinct(ViewEvent.user_id))).filter(
            ViewEvent.paste_id == paste_id,
            ViewEvent.user_id != None
        ).scalar() or 0
        
        unique_viewers = unique_ips + unique_users
        
        session_views = db.session.query(
            ViewEvent.session_id,
            func.count(ViewEvent.id).label('views')
        ).filter(
            ViewEvent.paste_id == paste_id,
            ViewEvent.session_id != None
        ).group_by(ViewEvent.session_id).all()
        
        avg_views_per_session = sum(s.views for s in session_views) / len(session_views) if session_views else 0
        
        return jsonify({
            "paste_id": paste_id,
            "total_views": total_views,
            "unique_viewers": unique_viewers,
            "avg_views_per_session": round(avg_views_per_session, 2),
            "last_updated": datetime.utcnow().isoformat()
        }), 200

@app.route('/api/system/metrics', methods=['GET'])
def get_system_metrics():
    """
    API: Get system-wide metrics
    """
    global event_count, event_start_time, processing_times, error_count, backfill_count
    
    time_elapsed = time.time() - event_start_time
    ingestion_rate = event_count / time_elapsed if time_elapsed > 0 else 0
    
    total_errors = sum(error_count.values())
    error_rate = (total_errors / event_count) * 100 if event_count > 0 else 0
    avg_latency = sum(processing_times) / len(processing_times) if processing_times else 0
    
    return jsonify({
        "event_ingestion_rate": round(ingestion_rate, 2),
        "error_rate": round(error_rate, 2),
        "processing_latency_ms": round(avg_latency * 1000, 2),
        "backfill_count": backfill_count,
        "total_events_processed": event_count,
        "error_details": error_count
    }), 200

@app.route('/api/backfill', methods=['POST'])
def backfill_events():
    """
    API: Backfill events from view service after an outage
    """
    global backfill_count
    
    try:
        events = request.json.get('events', [])
        
        if not events:
            return jsonify({"error": "No events provided"}), 400
        
        success_count = 0
        for event_data in events:
            try:
                if not all(k in event_data for k in ['paste_id', 'short_url', 'view_count']):
                    continue
                
                event = ViewEvent(
                    paste_id=event_data['paste_id'],
                    short_url=event_data['short_url'],
                    view_count=event_data['view_count'],
                    ip_address=event_data.get('ip_address'),
                    user_id=event_data.get('user_id'),
                    session_id=event_data.get('session_id') or str(uuid.uuid4()),
                    timestamp=datetime.fromisoformat(event_data.get('timestamp')) if event_data.get('timestamp') else datetime.utcnow(),
                    metadata=event_data.get('metadata')
                )
                
                db.session.add(event)
                event_queue.put(event.id)
                success_count += 1
                backfill_count += 1
                
            except Exception as e:
                error_count['processing'] += 1
                error = ProcessingError(
                    error_type='backfill',
                    error_message=str(e),
                    raw_data=str(event_data)
                )
                db.session.add(error)
        
        db.session.commit()
        return jsonify({
            "success": True, 
            "message": f"Backfilled {success_count} events successfully",
            "success_count": success_count,
            "total_events": len(events)
        }), 200
        
    except Exception as e:
        error_count['processing'] += 1
        try:
            error = ProcessingError(
                error_type='backfill',
                error_message=str(e),
                raw_data=str(request.data)
            )
            db.session.add(error)
            db.session.commit()
        except:
            pass
        
        return jsonify({"error": "Server error during backfill operation"}), 500

# Background worker to process events from the queue
def process_events():
    """
    Background worker to process events from the queue
    """
    while True:
        try:
            # Get event from queue with timeout
            try:
                event_id = event_queue.get(timeout=1)
            except queue.Empty:
                time.sleep(0.1)
                continue
            
            with app.app_context():
                # Get event from database
                event = ViewEvent.query.get(event_id)
                
                if not event or event.processed:
                    continue
                
                start_time = time.time()
                
                # Process event (update aggregates)
                aggregate = AnalyticsAggregate.query.filter_by(paste_id=event.paste_id).first()
                
                if not aggregate:
                    # Calculate base metrics
                    total_views = ViewEvent.query.filter_by(paste_id=event.paste_id).count()
                    
                    unique_ips = db.session.query(func.count(func.distinct(ViewEvent.ip_address))).filter(
                        ViewEvent.paste_id == event.paste_id,
                        ViewEvent.ip_address != None
                    ).scalar() or 0
                    
                    unique_users = db.session.query(func.count(func.distinct(ViewEvent.user_id))).filter(
                        ViewEvent.paste_id == event.paste_id,
                        ViewEvent.user_id != None
                    ).scalar() or 0
                    
                    unique_viewers = unique_ips + unique_users
                    
                    session_views = db.session.query(
                        ViewEvent.session_id,
                        func.count(ViewEvent.id).label('views')
                    ).filter(
                        ViewEvent.paste_id == event.paste_id,
                        ViewEvent.session_id != None
                    ).group_by(ViewEvent.session_id).all()
                    
                    avg_views_per_session = sum(s.views for s in session_views) / len(session_views) if session_views else 0
                    
                    # Create new aggregate
                    aggregate = AnalyticsAggregate(
                        paste_id=event.paste_id,
                        total_views=total_views,
                        unique_viewers=unique_viewers,
                        avg_views_per_session=avg_views_per_session,
                        last_updated=datetime.utcnow()
                    )
                    db.session.add(aggregate)
                else:
                    # Update existing aggregate
                    aggregate.total_views = ViewEvent.query.filter_by(paste_id=event.paste_id).count()
                    
                    unique_ips = db.session.query(func.count(func.distinct(ViewEvent.ip_address))).filter(
                        ViewEvent.paste_id == event.paste_id,
                        ViewEvent.ip_address != None
                    ).scalar() or 0
                    
                    unique_users = db.session.query(func.count(func.distinct(ViewEvent.user_id))).filter(
                        ViewEvent.paste_id == event.paste_id,
                        ViewEvent.user_id != None
                    ).scalar() or 0
                    
                    aggregate.unique_viewers = unique_ips + unique_users
                    
                    session_views = db.session.query(
                        ViewEvent.session_id,
                        func.count(ViewEvent.id).label('views')
                    ).filter(
                        ViewEvent.paste_id == event.paste_id,
                        ViewEvent.session_id != None
                    ).group_by(ViewEvent.session_id).all()
                    
                    aggregate.avg_views_per_session = sum(s.views for s in session_views) / len(session_views) if session_views else 0
                    aggregate.last_updated = datetime.utcnow()
                
                # Mark event as processed and record processing time
                event.processed = True
                event.processing_time = time.time() - start_time
                
                # Commit changes
                db.session.commit()
                
                # Signal task completion
                event_queue.task_done()
                
        except Exception as e:
            print(f"Error in background worker: {str(e)}")
            try:
                with app.app_context():
                    error = ProcessingError(
                        error_type='worker',
                        error_message=str(e),
                        raw_data='Background worker exception'
                    )
                    db.session.add(error)
                    db.session.commit()
            except:
                pass
            
            time.sleep(1)  # Avoid tight loop on persistent errors

# Start background worker in a separate thread
worker_thread = threading.Thread(target=process_events, daemon=True)

# Create database tables and start worker on application startup
with app.app_context():
    db.create_all()
    # Add default system metrics
    if SystemMetrics.query.count() == 0:
        default_metrics = [
            SystemMetrics(metric_name='event_ingestion_rate', metric_value=0.0),
            SystemMetrics(metric_name='error_rate', metric_value=0.0),
            SystemMetrics(metric_name='processing_latency', metric_value=0.0),
            SystemMetrics(metric_name='backfill_count', metric_value=0.0)
        ]
        db.session.bulk_save_objects(default_metrics)
        db.session.commit()

# Start worker thread
worker_thread.start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003, debug=True)