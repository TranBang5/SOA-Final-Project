from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pydantic import BaseModel
import datetime
import os
import secrets
import json
import pika
from dotenv import load_dotenv
from models import Base, Paste

load_dotenv()

app = FastAPI()

# Database configuration
DATABASE_URL = f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASS')}@{os.getenv('DB_HOST')}/{os.getenv('DB_NAME')}"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

# Create tables if they don't exist
Base.metadata.create_all(bind=engine)

# Pydantic models for request/response
class PasteCreate(BaseModel):
    content: str
    expires_in: int | None = None  # Expiration in minutes

class PasteResponse(BaseModel):
    id: int
    content: str
    url: str
    created_at: datetime.datetime
    expires_at: datetime.datetime | None

# Generate a random URL
def generate_random_url(length=10):
    return secrets.token_urlsafe(length)

# API endpoints
@app.post("/pastes/", response_model=PasteResponse)
async def create_paste(paste: PasteCreate):
    db = SessionLocal()
    try:
        # Generate unique URL
        url = generate_random_url()
        while db.query(Paste).filter(Paste.url == url).first():
            url = generate_random_url()  # Ensure URL is unique

        expires_at = None
        if paste.expires_in:
            expires_at = datetime.datetime.utcnow() + datetime.timedelta(minutes=paste.expires_in)
        
        db_paste = Paste(content=paste.content, url=url, expires_at=expires_at)
        db.add(db_paste)
        db.commit()
        db.refresh(db_paste)

        # Send event to RabbitMQ (for View Service)
        try:
            connection = pika.BlockingConnection(pika.ConnectionParameters(host="localhost"))
            channel = connection.channel()
            channel.queue_declare(queue="paste_created")
            paste_data = {
                "id": db_paste.id,
                "content": db_paste.content,
                "url": db_paste.url,
                "created_at": db_paste.created_at.isoformat(),
                "expires_at": db_paste.expires_at.isoformat() if db_paste.expires_at else None
            }
            channel.basic_publish(exchange="", routing_key="paste_created", body=json.dumps(paste_data))
            connection.close()
        except Exception as e:
            print(f"Failed to send event to RabbitMQ: {e}")

        return db_paste
    finally:
        db.close()

@app.get("/pastes/{paste_id}", response_model=PasteResponse)
async def get_paste(paste_id: int):
    db = SessionLocal()
    try:
        paste = db.query(Paste).filter(Paste.id == paste_id).first()
        if not paste:
            raise HTTPException(status_code=404, detail="Paste not found")
        return paste
    finally:
        db.close()

@app.get("/pastes/by-url/{url}", response_model=PasteResponse)
async def get_paste_by_url(url: str):
    db = SessionLocal()
    try:
        paste = db.query(Paste).filter(Paste.url == url).first()
        if not paste:
            raise HTTPException(status_code=404, detail="Paste not found")
        return paste
    finally:
        db.close()