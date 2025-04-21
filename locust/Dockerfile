FROM python:3.9-slim

# Install Locust
RUN pip install locust

# Set working directory
WORKDIR /app

# Copy Locust file
COPY locustfile.py .

# Expose Locust web interface port
EXPOSE 5089

# Run Locust
CMD ["locust", "-f", "locustfile.py", "--host=http://view-service:5002", "--web-host=0.0.0.0", "--web-port=5089"]