# Use a lightweight official Python image
FROM python:3.11-slim

# Set working directory in the container
WORKDIR /app

# Install system dependencies (for MySQL client and compilation)
RUN apt-get update && \
    apt-get install -y gcc default-libmysqlclient-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy all app files into the container
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose the Flask app port
EXPOSE 5001

# Start the Flask app using Gunicorn
CMD ["gunicorn", "-w", "5", "-b", "0.0.0.0:5000", "app:app"]
