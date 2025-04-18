FROM python:3.8-alpine

WORKDIR /app

# Install system dependencies
RUN apk add --no-cache \
    build-base

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

EXPOSE 5000

# Use Gunicorn instead of Flask development server
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"] 