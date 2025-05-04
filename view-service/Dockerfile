# Use official Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code into container
COPY . .

RUN pip install --no-cache-dir gevent mysql-connector-python
ENV DB_POOL_SIZE=32
CMD ["gunicorn", "--worker-class", "gevent", "-w", "5", "--threads", "50", "--worker-tmp-dir", "/dev/shm", "--timeout", "20", "--keep-alive", "3", "--log-level", "info", "--access-logfile", "-", "--error-logfile", "-", "-b", "0.0.0.0:5002", "app:app"]
