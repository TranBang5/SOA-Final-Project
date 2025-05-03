import random
import string
from datetime import datetime, timedelta
import secrets
from faker import Faker
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from paste_service.app import Paste, db  # Adjust import based on your project structure
import redis

# Database configuration (match paste-service)
DATABASE_URL = 'mysql+mysqlconnector://view_user:view_pass@view-db:3306/view_db'
REDIS_URL = 'redis://redis:6379/0'

# Initialize Faker and Redis
fake = Faker()
redis_client = redis.Redis(host='redis', port=6379, db=0)

def generate_url(length=10):
    """Generate a unique URL-safe string."""
    return secrets.token_urlsafe(length)

def generate_content(min_words=500, max_words=5000):
    """Generate random content with specified word count."""
    word_count = random.randint(min_words, max_words)
    words = [fake.word() for _ in range(word_count)]
    return ' '.join(words)

def populate_pastes(num_records=10000, hot_paste_count=1000):
    """Populate the Paste table with num_records entries, marking hot_paste_count as hot."""
    # Create database engine and session
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        print(f"Starting to populate {num_records} paste records...")
        existing_urls = set(session.query(Paste.url).all())
        hot_urls = []

        for i in range(num_records):
            # Generate unique URL
            url = generate_url()
            while url in existing_urls:
                url = generate_url()
            existing_urls.add(url)

            # Generate content (500–5000 words)
            content = generate_content()

            # Set random expiration (50% no expiration, 50% 1–30 days)
            expires_in = random.choice([None, random.randint(1, 30) * 1440])
            expires_at = (datetime.utcnow() + timedelta(minutes=expires_in)) if expires_in else None

            # Create paste
            paste = Paste(
                url=url,
                content=content,
                created_at=datetime.utcnow(),
                expires_at=expires_at
            )

            session.add(paste)

            # Mark first 1000 pastes as hot
            if i < hot_paste_count:
                hot_urls.append(url)

            # Commit every 100 records
            if (i + 1) % 100 == 0:
                session.commit()
                print(f"Committed {i + 1} records")

        # Final commit
        session.commit()

        # Store hot URLs in Redis
        redis_client.delete('hot_pastes')
        for url in hot_urls:
            redis_client.rpush('hot_pastes', url)
        print(f"Stored {len(hot_urls)} hot paste URLs in Redis.")

        print(f"Successfully populated {num_records} paste records.")

    except Exception as e:
        session.rollback()
        print(f"Error populating database: {e}")
    finally:
        session.close()

if __name__ == '__main__':
    populate_pastes()
