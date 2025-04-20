import os
import requests
import logging
import time
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database setup
DATABASE_URL = os.getenv('DATABASE_URL', 'mysql+mysqlconnector://cleanup_user:cleanup_pass@cleanup-db/cleanup_db')
engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20)
Session = sessionmaker(bind=engine)
Base = declarative_base()

# Constants
REQUEST_TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', '5'))
CLEANUP_INTERVAL = int(os.getenv('CLEANUP_INTERVAL', '3600'))
PASTE_SERVICE_URL = os.getenv('PASTE_SERVICE_URL', 'http://paste-service:5001')
ANALYTIC_SERVICE_URL = os.getenv('ANALYTIC_SERVICE_URL', 'http://analytic-service:5003')

# Model
class Paste(Base):
    __tablename__ = 'paste'

    paste_id = Column(Integer, primary_key=True)
    short_url = Column(String(10), nullable=False)
    content = Column(Text, nullable=False)
    expires_at = Column(DateTime)
    view_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    is_deleted = Column(Boolean, default=False)
    deleted_at = Column(DateTime)

# Helper functions
def delete_from_paste_service(paste_id):
    response = requests.delete(
        f"{PASTE_SERVICE_URL}/api/paste/{paste_id}",
        timeout=REQUEST_TIMEOUT
    )
    response.raise_for_status()

def delete_from_analytic_service(paste_id):
    response = requests.delete(
        f"{ANALYTIC_SERVICE_URL}/api/paste/{paste_id}",
        timeout=REQUEST_TIMEOUT
    )
    response.raise_for_status()

# Cleanup logic
def cleanup_expired_pastes():
    while True:
        session = Session()
        try:
            logger.info("Starting cleanup of expired pastes")
            now = datetime.utcnow()
            expired_pastes = session.query(Paste).filter(
                Paste.expires_at <= now,
                Paste.is_deleted == False
            ).all()

            if expired_pastes:
                logger.info(f"Found {len(expired_pastes)} expired pastes to delete")
                for paste in expired_pastes:
                    paste_id = paste.paste_id
                    paste.is_deleted = True
                    paste.deleted_at = now

                    try:
                        delete_from_paste_service(paste_id)
                        delete_from_analytic_service(paste_id)
                        logger.info(f"Deleted paste {paste_id} from all services")
                    except Exception as e:
                        logger.error(f"Error deleting paste {paste_id}: {str(e)}")

                session.commit()
                logger.info("Cleanup completed")
            else:
                logger.info("No expired pastes found")

        except Exception as e:
            logger.error(f"Cleanup failed: {str(e)}")
            session.rollback()
        finally:
            session.close()

        logger.info(f"Next cleanup in {CLEANUP_INTERVAL} seconds")
        time.sleep(CLEANUP_INTERVAL)

# Initialize tables if not exist
Base.metadata.create_all(engine)

if __name__ == '__main__':
    logger.info("Cleanup service started")
    cleanup_expired_pastes()
