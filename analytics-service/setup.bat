@echo off
echo Setting up dependencies for Analytics Microservice...

:: Check if Python is installed
python --version > nul 2>&1
if %errorlevel% neq 0 (
    echo Python is not installed. Please install Python 3.8 or higher.
    echo Download from: https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Install required Python packages
echo Installing Python dependencies...
pip install Flask==2.2.3 Flask-SQLAlchemy==3.0.3 mysql-connector-python==8.0.32 SQLAlchemy==1.4.46 requests==2.28.2 gunicorn==20.1.0

:: Check if Docker is installed
docker --version > nul 2>&1
if %errorlevel% neq 0 (
    echo Docker is not installed. Please install Docker Desktop for Windows.
    echo Download from: https://www.docker.com/products/docker-desktop/
    pause
    exit /b 1
)

:: Check if Docker Compose is installed
docker-compose --version > nul 2>&1
if %errorlevel% neq 0 (
    echo Docker Compose is not installed. It should be included with Docker Desktop.
    echo If not, please install it manually.
    pause
    exit /b 1
)

echo All dependencies are installed and ready!
echo To run the analytics microservice:
echo 1. Navigate to the analytics-service directory
echo 2. Run: docker-compose up -d
echo 3. Access the service at: http://localhost:5003
pause