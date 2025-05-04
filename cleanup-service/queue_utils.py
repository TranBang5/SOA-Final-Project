import os
import logging
from datetime import datetime
from rq import Queue
from redis import Redis
from dotenv import load_dotenv

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

# Create RQ queue
delete_queue = Queue('delete_paste', connection=redis_conn)

def enqueue_paste_deletion(paste_id, expires_at):
    """
    Enqueue a paste deletion job to be executed at the expiration time.
    
    Args:
        paste_id (int): The ID of the paste to delete
        expires_at (datetime): The time when the paste should be deleted
        
    Returns:
        job: The RQ job object
    """
    # Calculate delay in seconds
    now = datetime.utcnow()
    delay = (expires_at - now).total_seconds()
    
    # If the paste has already expired, set a small delay
    if delay <= 0:
        delay = 1
    
    logger.info(f"Enqueueing deletion of paste {paste_id} in {delay} seconds")
    
    # Enqueue the job with the calculated delay
    job = delete_queue.enqueue_in(
        'delete_paste',
        delay,
        'delete_paste',
        args=[paste_id],
        job_id=f"delete_paste_{paste_id}"
    )
    
    return job 