#!/bin/bash

# Tide Billing Production Deployment Script
# Run this script to deploy the application in production

set -e  # Exit on any error

echo "🚀 Starting Tide Billing Deployment..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Docker and Docker Compose are installed
check_dependencies() {
    print_status "Checking dependencies..."
    
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    
    print_status "Dependencies check passed ✓"
}

# Create production environment file if it doesn't exist
setup_environment() {
    print_status "Setting up environment..."
    
    if [ ! -f .env ]; then
        if [ -f .env.production ]; then
            cp .env.production .env
            print_warning "Created .env file from .env.production template."
            print_warning "Please update the values in .env file before proceeding."
            read -p "Press Enter to continue after updating .env file..."
        else
            print_error ".env file not found and no template available."
            exit 1
        fi
    else
        print_status "Environment file found ✓"
    fi
}

# Create necessary directories
create_directories() {
    print_status "Creating necessary directories..."
    
    mkdir -p logs
    mkdir -p nginx
    mkdir -p backups
    
    print_status "Directories created ✓"
}

# Build and start services
deploy_services() {
    print_status "Building and starting services..."
    
    # Pull latest images
    docker-compose pull
    
    # Build the application
    docker-compose build --no-cache
    
    # Start services
    docker-compose up -d
    
    print_status "Services started ✓"
}

# Wait for services to be ready
wait_for_services() {
    print_status "Waiting for services to be ready..."
    
    # Wait for database
    print_status "Waiting for database..."
    docker-compose exec -T db pg_isready -U ${POSTGRES_USER:-tidedbu} || sleep 5
    
    # Wait for Redis
    print_status "Waiting for Redis..."
    docker-compose exec -T redis redis-cli ping || sleep 5
    
    print_status "Services are ready ✓"
}

# Run database migrations
run_migrations() {
    print_status "Running database migrations..."
    
    docker-compose exec -T web python tidebilling/manage.py migrate

    print_status "Migrations completed ✓"
}

# Provision the admin/billing/readonly role groups (idempotent)
setup_roles() {
    print_status "Setting up role groups..."

    docker-compose exec -T web python tidebilling/manage.py setup_roles

    print_status "Role groups ready ✓"
}

# Create superuser if it doesn't exist
create_superuser() {
    print_status "Creating superuser..."
    
    docker-compose exec -T web python tidebilling/manage.py shell << EOF
from django.contrib.auth.models import User
if not User.objects.filter(is_superuser=True).exists():
    User.objects.create_superuser('admin', 'admin@tidebilling.com', 'admin123')
    print('Superuser created: admin/admin123')
else:
    print('Superuser already exists')
EOF
    
    print_status "Superuser setup completed ✓"
}

# Collect static files
collect_static() {
    print_status "Collecting static files..."
    
    docker-compose exec -T web python tidebilling/manage.py collectstatic --noinput
    
    print_status "Static files collected ✓"
}

# Setup SSL certificates (placeholder)
setup_ssl() {
    print_status "SSL certificate setup..."
    
    if [ "$ENVIRONMENT" = "production" ]; then
        print_warning "Please configure SSL certificates manually."
        print_warning "Update nginx/default.conf with your SSL certificate paths."
    else
        print_status "SSL setup skipped for non-production environment ✓"
    fi
}

# Health check
health_check() {
    print_status "Running health checks..."
    
    # Check if web service is responding
    if curl -f http://localhost:${WEB_PORT:-8000}/health/ > /dev/null 2>&1; then
        print_status "Web service health check passed ✓"
    else
        print_warning "Web service health check failed. Service might still be starting..."
    fi
    
    # Check if all containers are running
    if [ "$(docker-compose ps -q | wc -l)" -eq "$(docker-compose ps -q --filter status=running | wc -l)" ]; then
        print_status "All containers are running ✓"
    else
        print_warning "Some containers might not be running properly."
        docker-compose ps
    fi
}

# Main deployment function
main() {
    echo "🏗️  Tide Billing Production Deployment"
    echo "======================================"
    
    check_dependencies
    setup_environment
    create_directories
    deploy_services
    wait_for_services
    run_migrations
    setup_roles
    create_superuser
    collect_static
    setup_ssl
    health_check
    
    echo ""
    echo "🎉 Deployment completed successfully!"
    echo ""
    echo "📊 Service URLs:"
    echo "   Web Application: http://localhost:${WEB_PORT:-8000}"
    echo "   Admin Interface: http://localhost:${WEB_PORT:-8000}/admin"
    echo "   API Documentation: http://localhost:${WEB_PORT:-8000}/api/docs"
    echo ""
    echo "🔐 Default Admin Credentials:"
    echo "   Username: admin"
    echo "   Password: admin123"
    echo "   Please change these credentials immediately!"
    echo ""
    echo "📝 Next Steps:"
    echo "   1. Update admin password"
    echo "   2. Configure SSL certificates for production"
    echo "   3. Set up monitoring and backups"
    echo "   4. Review and update environment variables"
    echo ""
    echo "🐳 Useful Commands:"
    echo "   View logs: docker-compose logs -f"
    echo "   Stop services: docker-compose down"
    echo "   Restart services: docker-compose restart"
    echo "   Update services: docker-compose pull && docker-compose up -d"
    echo ""
}

# Handle script arguments
case "${1:-deploy}" in
    "deploy")
        main
        ;;
    "stop")
        print_status "Stopping services..."
        docker-compose down
        print_status "Services stopped ✓"
        ;;
    "restart")
        print_status "Restarting services..."
        docker-compose restart
        print_status "Services restarted ✓"
        ;;
    "logs")
        docker-compose logs -f
        ;;
    "backup")
        print_status "Creating backup..."
        mkdir -p backups
        docker-compose exec -T db pg_dump -U ${POSTGRES_USER:-tidedbu} ${POSTGRES_DB:-tide} > backups/backup_$(date +%Y%m%d_%H%M%S).sql
        print_status "Backup created ✓"
        ;;
    "status")
        docker-compose ps
        health_check
        ;;
    *)
        echo "Usage: $0 {deploy|stop|restart|logs|backup|status}"
        echo ""
        echo "Commands:"
        echo "  deploy  - Full deployment (default)"
        echo "  stop    - Stop all services"
        echo "  restart - Restart all services"
        echo "  logs    - Show service logs"
        echo "  backup  - Create database backup"
        echo "  status  - Show service status"
        exit 1
        ;;
esac