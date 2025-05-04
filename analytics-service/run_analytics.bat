@echo off
echo Starting Analytics Service...
docker-compose up --build -d
echo Analytics Service is running!
echo Access it at http://localhost:5003