import os
import logging
from datetime import datetime
from rq import Worker, Queue, Connection
from redis import Redis
from dotenv import load_dotenv
from app import delete_from_paste_service, delete_from_analytic_service, Session, Paste

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Redis connection
REDIS_HOST = os.getenv('REDIS_HOST', 'redis')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
REDIS_DB = int(os.getenv('REDIS_DB', '0'))

# Create Redis connection
redis_conn = Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB
)

def delete_paste(paste_id):
    """
    Delete a paste from all services.
    
    Args:
        paste_id (int): The ID of the paste to delete
    """
    logger.info(f"Processing deletion job for paste {paste_id}")
    
    session = Session()
    try:
        # Get the paste from the database
        paste = session.query(Paste).filter_by(paste_id=paste_id).first()
        
        if not paste:
            logger.warning(f"Paste {paste_id} not found in database")
            return
        
        # Check if the paste is already deleted
        if paste.is_deleted:
            logger.info(f"Paste {paste_id} is already deleted")
            return
        
        # Mark the paste as deleted
        paste.is_deleted = True
        paste.deleted_at = datetime.utcnow()
        
        # Delete from paste service
        delete_from_paste_service(paste_id)
        
        # Delete from analytic service
        delete_from_analytic_service(paste_id)
        
        # Commit the changes
        session.commit()
        
        logger.info(f"Successfully deleted paste {paste_id}")
        
    except Exception as e:
        logger.error(f"Error deleting paste {paste_id}: {str(e)}")
        session.rollback()
    finally:
        session.close()

if __name__ == '__main__':
    # Define the queue
    delete_queue = Queue('delete_paste', connection=redis_conn)
    
    # Start the worker
    with Connection(redis_conn):
        worker = Worker([delete_queue])
        logger.info("Starting RQ worker for paste deletion")
        worker.work()