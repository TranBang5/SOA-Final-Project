# Pastebin Microservices

A modern, scalable implementation of a Pastebin-like service using a microservices architecture. This project demonstrates the use of multiple independent services working together to provide a robust paste-sharing platform.

## Architecture

The system consists of four main microservices:

1. **API Gateway** (Port 5000)
   - Entry point for all client requests
   - Handles request routing to appropriate services
   - Manages service discovery and load balancing

2. **Auth Service** (Port 5001)
   - Manages user authentication and authorization
   - Handles user registration and login
   - Issues and validates JWT tokens
   - Uses dedicated MySQL database

3. **Paste Service** (Port 5002)
   - Core service for managing paste operations
   - Creates, reads, updates, and deletes pastes
   - Integrates with Auth Service for user verification
   - Uses dedicated MySQL database

4. **Analytics Service** (Port 5003)
   - Tracks paste statistics and metrics
   - Provides insights on paste usage
   - Uses dedicated MySQL database

## Prerequisites

- Docker
- Docker Compose
- Git

## Getting Started

1. Clone the repository:
```bash
git clone [repository-url]
cd pastebin-microservices
```

2. Build the services:
```bash
docker-compose build
```

3. Start the services:
```bash
docker-compose up -d
```

4. The services will be available at:
   - API Gateway: http://localhost:5000
   - Auth Service: http://localhost:5001
   - Paste Service: http://localhost:5002
   - Analytics Service: http://localhost:5003

## Environment Variables

Each service has its own environment variables configured in the docker-compose.yml:

### API Gateway
- `AUTH_SERVICE_URL`: URL for the authentication service
- `PASTE_SERVICE_URL`: URL for the paste service
- `ANALYTICS_SERVICE_URL`: URL for the analytics service

### Auth Service
- `DATABASE_URL`: MySQL connection string
- `JWT_SECRET_KEY`: Secret key for JWT token generation

### Paste Service
- `DATABASE_URL`: MySQL connection string
- `AUTH_SERVICE_URL`: URL for the authentication service
- `ANALYTICS_SERVICE_URL`: URL for the analytics service

### Analytics Service
- `DATABASE_URL`: MySQL connection string

## Database Configuration

Each service has its own MySQL database with the following default credentials:

- Auth DB:
  - Database: auth
  - User: auth_user
  - Password: auth_pass

- Paste DB:
  - Database: paste
  - User: paste_user
  - Password: paste_pass

- Analytics DB:
  - Database: analytics
  - User: analytics_user
  - Password: analytics_pass

## Data Persistence

All database data is persisted using Docker volumes:
- auth_data
- paste_data
- analytics_data

## Stopping the Services

To stop all services:
```bash
docker-compose down
```

To stop all services and remove volumes:
```bash
docker-compose down -v
```

## Security Note

For production deployment, make sure to:
1. Change all default passwords
2. Use proper JWT secret keys
3. Enable HTTPS/TLS
4. Implement proper network security measures

## Contributing

Please read CONTRIBUTING.md for details on our code of conduct and the process for submitting pull requests.

## License

This project is licensed under the MIT License - see the LICENSE file for details. 