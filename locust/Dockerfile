FROM python:3.11-slim
WORKDIR /app
COPY ../locust/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8089 5557
CMD ["locust", "-f", "locustfile.py"]
