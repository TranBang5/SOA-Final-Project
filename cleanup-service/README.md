# Cleanup Service

The Cleanup Service is a microservice responsible for managing expired pastes in the Paste Sharing System. It periodically checks for expired pastes, marks them as deleted, and notifies the Analytic Service.

## Features

- Periodic cleanup of expired pastes
- Manual cleanup trigger via API
- Synchronization with View Service
- Health check endpoint for container orchestration
- Comprehensive logging and error handling

## Architecture

The Cleanup Service runs as a background process that periodically checks for expired pastes. It maintains its own database to track paste status and communicates with other services in the system:

- **View Service**: To sync paste data
- **Analytic Service**: To notify about deleted pastes

## Prerequisites

- Python 3.9+
- Docker and Docker Compose (for containerized deployment)
- MySQL 8.0+ (for standalone deployment)

## Configuration

The service can be configured using environment variables:

| Variable               | Description                              | Default                                                                  |
| ---------------------- | ---------------------------------------- | ------------------------------------------------------------------------ |
| `DATABASE_URL`         | MySQL connection string                  | `mysql+mysqlconnector://cleanup_user:cleanup_pass@cleanup-db/cleanup_db` |
| `VIEW_SERVICE_URL`     | URL of the View Service                  | `http://view-service:5002`                                               |
| `ANALYTIC_SERVICE_URL` | URL of the Analytic Service              | `http://analytic-service:5003`                                           |
| `REQUEST_TIMEOUT`      | Timeout for HTTP requests in seconds     | `5`                                                                      |
| `CLEANUP_INTERVAL`     | Interval between cleanup runs in seconds | `3600` (1 hour)                                                          |

## Running Standalone

1. Clone the repository:

   ```bash
   git clone <repository-url>
   cd cleanup-service
   ```

2. Create a virtual environment and install dependencies:

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Create a `.env` file with your configuration:

   ```
   DATABASE_URL=mysql+mysqlconnector://cleanup_user:cleanup_pass@localhost/cleanup_db
   VIEW_SERVICE_URL=http://localhost:5002
   ANALYTIC_SERVICE_URL=http://localhost:5003
   REQUEST_TIMEOUT=5
   CLEANUP_INTERVAL=3600
   ```

4. Run the service:
   ```bash
   python app.py
   ```

## Running with Docker

1. Build and run using Docker Compose:

   ```bash
   docker-compose up -d
   ```

2. Check the logs:
   ```bash
   docker-compose logs -f cleanup-service
   ```

## API Endpoints

| Endpoint       | Method | Description                          |
| -------------- | ------ | ------------------------------------ |
| `/api/health`  | GET    | Health check endpoint                |
| `/api/cleanup` | POST   | Manually trigger the cleanup process |
| `/api/sync`    | POST   | Sync pastes from the View Service    |

## Integration with Other Services

### View Service Integration

The Cleanup Service periodically syncs with the View Service to get the latest paste data. This ensures that the Cleanup Service has up-to-date information about paste expiration times.

### Analytic Service Integration

When a paste is marked as deleted, the Cleanup Service notifies the Analytic Service. This allows the Analytic Service to track deletion events and update its analytics accordingly.

## Troubleshooting

- **Service not starting**: Check the logs for database connection issues or configuration errors.
- **Cleanup not running**: Verify that the `CLEANUP_INTERVAL` is set correctly and that the service has access to the database.
- **Sync failures**: Ensure that the View Service is running and accessible.

## License

[Your License]
