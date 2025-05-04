import os
import requests
import logging
import time
from datetime import datetime
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
REQUEST_TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', '5'))
CLEANUP_INTERVAL = int(os.getenv('CLEANUP_INTERVAL', '3600'))
RETRY_ATTEMPTS = int(os.getenv('RETRY_ATTEMPTS', '3'))
RETRY_DELAY = float(os.getenv('RETRY_DELAY', '1'))
PASTE_SERVICE_URL = os.getenv('PASTE_SERVICE_URL', 'http://paste-service:5000')
VIEW_SERVICE_URL = os.getenv('VIEW_SERVICE_URL', 'http://view-service:5002')
ANALYTIC_SERVICE_URL = os.getenv('ANALYTIC_SERVICE_URL', 'http://analytic-service:5003')

# Helper functions with retry mechanism
@retry(
    stop=stop_after_attempt(RETRY_ATTEMPTS),
    wait=wait_fixed(RETRY_DELAY),
    retry=retry_if_exception_type((requests.RequestException, requests.HTTPError)),
    reraise=True
)
def get_expired_pastes_from_service(service_url, service_name):
    try:
        response = requests.get(
            f"{service_url}/api/pastes/expired",
            timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        pastes = response.json().get('data', [])
        logger.info(f"Retrieved {len(pastes)} expired pastes from {service_name}")
        return pastes
    except Exception as e:
        logger.error(f"Failed to retrieve expired pastes from {service_name}: {str(e)}")
        raise

@retry(
    stop=stop_after_attempt(RETRY_ATTEMPTS),
    wait=wait_fixed(RETRY_DELAY),
    retry=retry_if_exception_type((requests.RequestException, requests.HTTPError)),
    reraise=True
)
def delete_from_paste_service(paste_id):
    response = requests.delete(
        f"{PASTE_SERVICE_URL}/api/paste/{paste_id}",
        timeout=REQUEST_TIMEOUT
    )
    response.raise_for_status()
    logger.info(f"Successfully deleted paste {paste_id} from Paste Service")

@retry(
    stop=stop_after_attempt(RETRY_ATTEMPTS),
    wait=wait_fixed(RETRY_DELAY),
    retry=retry_if_exception_type((requests.RequestException, requests.HTTPError)),
    reraise=True
)
def delete_from_view_service(paste_id):
    response = requests.delete(
        f"{VIEW_SERVICE_URL}/api/paste/{paste_id}",
        timeout=REQUEST_TIMEOUT
    )
    response.raise_for_status()
    logger.info(f"Successfully deleted paste {paste_id} from View Service")

@retry(
    stop=stop_after_attempt(RETRY_ATTEMPTS),
    wait=wait_fixed(RETRY_DELAY),
    retry=retry_if_exception_type((requests.RequestException, requests.HTTPError)),
    reraise=True
)
def delete_from_analytic_service(paste_id):
    response = requests.delete(
        f"{ANALYTIC_SERVICE_URL}/api/paste/{paste_id}",
        timeout=REQUEST_TIMEOUT
    )
    response.raise_for_status()
    logger.info(f"Successfully deleted paste {paste_id} from Analytic Service")

# Cleanup logic
def cleanup_expired_pastes():
    while True:
        try:
            logger.info("Starting cleanup of expired pastes")
            # Lấy danh sách paste hết hạn từ các service
            paste_service_pastes = []
            view_service_pastes = []
            analytic_service_pastes = []

            try:
                paste_service_pastes = get_expired_pastes_from_service(PASTE_SERVICE_URL, "Paste Service")
            except Exception as e:
                logger.warning(f"Skipping Paste Service due to error: {str(e)}")

            try:
                view_service_pastes = get_expired_pastes_from_service(VIEW_SERVICE_URL, "View Service")
            except Exception as e:
                logger.warning(f"Skipping View Service due to error: {str(e)}")

            try:
                analytic_service_pastes = get_expired_pastes_from_service(ANALYTIC_SERVICE_URL, "Analytic Service")
            except Exception as e:
                logger.warning(f"Skipping Analytic Service due to error: {str(e)}")

            # Kết hợp và loại bỏ trùng lặp dựa trên paste_id
            all_pastes = {}
            for paste in paste_service_pastes + view_service_pastes + analytic_service_pastes:
                paste_id = paste.get('paste_id')
                if paste_id and paste_id not in all_pastes:
                    all_pastes[paste_id] = paste

            expired_pastes = list(all_pastes.values())
            if expired_pastes:
                logger.info(f"Found {len(expired_pastes)} unique expired pastes to delete")
                for paste in expired_pastes:
                    paste_id = paste.get('paste_id')
                    success = True

                    # Thử xóa từ tất cả các service
                    try:
                        delete_from_paste_service(paste_id)
                    except Exception as e:
                        logger.error(f"Failed to delete paste {paste_id} from Paste Service: {str(e)}")
                        success = False

                    try:
                        delete_from_view_service(paste_id)
                    except Exception as e:
                        logger.error(f"Failed to delete paste {paste_id} from View Service: {str(e)}")
                        success = False

                    try:
                        delete_from_analytic_service(paste_id)
                    except Exception as e:
                        logger.error(f"Failed to delete paste {paste_id} from Analytic Service: {str(e)}")
                        success = False

                    if success:
                        logger.info(f"Successfully cleaned up paste {paste_id} from all services")
                    else:
                        logger.warning(f"Partial failure in cleaning up paste {paste_id}")

                logger.info("Cleanup completed successfully")
            else:
                logger.info("No expired pastes found")

        except Exception as e:
            logger.error(f"Cleanup failed: {str(e)}")

        logger.info(f"Next cleanup in {CLEANUP_INTERVAL} seconds")
        time.sleep(CLEANUP_INTERVAL)

if __name__ == '__main__':
    logger.info("Cleanup service started")
    cleanup_expired_pastes()
