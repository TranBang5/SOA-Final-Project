from flask import Flask, request, jsonify
import os
import mysql.connector
from datetime import datetime

app = Flask(__name__)

# Database configuration
db_config = {
    'host': os.getenv('MYSQL_HOST', 'view-db'),
    'user': os.getenv('MYSQL_USER', 'root'),
    'password': os.getenv('MYSQL_PASSWORD', 'root'),
    'database': os.getenv('MYSQL_DATABASE', 'view_service')
}

def get_db_connection():
    return mysql.connector.connect(**db_config)

@app.route('/view/<int:paste_id>', methods=['GET'])
def record_view(paste_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Record the view
        cursor.execute(
            "INSERT INTO views (paste_id, viewed_at) VALUES (%s, %s)",
            (paste_id, datetime.now())
        )
        conn.commit()
        
        cursor.close()
        conn.close()
        
        return jsonify({'message': 'View recorded'}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/views/<int:paste_id>', methods=['GET'])
def get_views(paste_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get total views
        cursor.execute(
            "SELECT COUNT(*) FROM views WHERE paste_id = %s",
            (paste_id,)
        )
        total_views = cursor.fetchone()[0]
        
        # Get recent views
        cursor.execute(
            "SELECT viewed_at FROM views WHERE paste_id = %s ORDER BY viewed_at DESC LIMIT 10",
            (paste_id,)
        )
        recent_views = [row[0].isoformat() for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'paste_id': paste_id,
            'total_views': total_views,
            'recent_views': recent_views
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003) 