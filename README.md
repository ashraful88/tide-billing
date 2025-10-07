# 🌊 Tide Billing

A comprehensive, production-ready billing and subscription management system built with Django, featuring robust API endpoints, automated recurring billing, payment processing, and service management.

## 🚀 Features

### Core Functionality
- **Customer Management**: Complete customer profiles with contacts and billing information
- **Product Catalog**: Products with categories, subcategories, tags, and inventory management
- **Order Processing**: Full order lifecycle from creation to fulfillment
- **Invoice Management**: Automated invoice generation, recurring billing, and payment tracking
- **Payment Processing**: Multiple payment gateways (Stripe, PayPal) with stored payment methods
- **Subscription Management**: Flexible subscription plans with trial periods and usage tracking
- **Service Management**: Professional service requests with time tracking and deliverables

### Technical Features
- **RESTful API**: Comprehensive API with OpenAPI documentation
- **Security**: Production-ready security configurations and rate limiting
- **Scalability**: Containerized deployment with Docker and Redis caching
- **Background Tasks**: Celery for async processing and scheduled tasks
- **Monitoring**: Comprehensive logging and health checks
- **Admin Interface**: Django admin with custom configurations

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│     Frontend    │    │    Load Balancer │    │     Nginx       │
│   (Optional)    │◄──►│     (Nginx)     │◄──►│   Static Files  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │
                                ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Django Web    │    │     Celery      │    │     Redis       │
│   Application   │◄──►│    Workers      │◄──►│   Cache/Queue   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │
         ▼
┌─────────────────┐
│   PostgreSQL    │
│    Database     │
└─────────────────┘
```

## 🔧 Technology Stack

- **Backend**: Django 5.2.2 + Django REST Framework
- **Database**: PostgreSQL 15
- **Cache/Queue**: Redis 7
- **Task Queue**: Celery
- **Web Server**: Nginx + Gunicorn
- **Containerization**: Docker + Docker Compose
- **Payment Processing**: Stripe, PayPal
- **API Documentation**: OpenAPI/Swagger

## 📋 Prerequisites

- Docker and Docker Compose
- Git
- Domain name (for production)
- SSL certificate (for production)
- Payment gateway accounts (Stripe, PayPal)

## 🚀 Quick Start (Development)

1. **Clone the repository**
   ```bash
   git clone https://github.com/ashraful88/tide-billing.git
   cd tide-billing
   ```

2. **Copy environment file**
   ```bash
   cp example.env .env
   # Edit .env with your configuration
   ```

3. **Start development services**
   ```bash
   docker-compose up -d
   ```

4. **Run migrations and create superuser**
   ```bash
   docker-compose exec web python tidebilling/manage.py migrate
   docker-compose exec web python tidebilling/manage.py createsuperuser
   ```

5. **Access the application**
   - Web App: http://localhost:8000
   - Admin: http://localhost:8000/admin
   - API Docs: http://localhost:8000/api/docs

## 🏭 Production Deployment

### Automated Deployment

Use the provided deployment script for easy setup:

```bash
# Make script executable
chmod +x deploy.sh

# Run full deployment
./deploy.sh deploy

# Other commands
./deploy.sh stop     # Stop services
./deploy.sh restart  # Restart services
./deploy.sh logs     # View logs
./deploy.sh backup   # Create backup
./deploy.sh status   # Check status
```

### Manual Deployment

1. **Prepare production environment**
   ```bash
   cp .env.production .env
   # Update .env with production values
   ```

2. **Configure SSL certificates**
   ```bash
   # Update nginx/default.conf with your SSL certificate paths
   # Obtain certificates from Let's Encrypt or your provider
   ```

3. **Deploy services**
   ```bash
   docker-compose -f docker-compose.yml up -d
   ```

4. **Run initial setup**
   ```bash
   docker-compose exec web python tidebilling/manage.py migrate
   docker-compose exec web python tidebilling/manage.py collectstatic --noinput
   docker-compose exec web python tidebilling/manage.py createsuperuser
   ```

## 🔧 Configuration

### Environment Variables

Key environment variables to configure:

```bash
# Security
SECRET_KEY=your-super-secret-key
DEBUG=False
ALLOWED_HOSTS=your-domain.com,www.your-domain.com

# Database
POSTGRES_HOST=db
POSTGRES_DB=tide
POSTGRES_USER=tidedbu
POSTGRES_PASSWORD=secure-password

# Email
EMAIL_HOST=smtp.gmail.com
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password

# Payment Gateways
STRIPE_SECRET_KEY=sk_live_your_stripe_key
PAYPAL_CLIENT_ID=your_paypal_client_id

# Business Settings
CURRENCY_CODE=USD
TAX_RATE=0.10
```

### Payment Gateway Setup

#### Stripe
1. Create account at https://stripe.com
2. Get API keys from dashboard
3. Set `STRIPE_PUBLISHABLE_KEY` and `STRIPE_SECRET_KEY`

#### PayPal
1. Create developer account at https://developer.paypal.com
2. Create application and get credentials
3. Set `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET`

## 📊 API Documentation

The API is fully documented and accessible at:
- **Swagger UI**: `/api/docs/`
- **ReDoc**: `/api/redoc/`
- **OpenAPI Schema**: `/api/schema/`

### Authentication

Use token-based authentication:

```bash
# Get token
curl -X POST http://localhost:8000/api/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'

# Use token in requests
curl -H "Authorization: Token your-token-here" \
  http://localhost:8000/api/v1/customers/
```

### Key Endpoints

```
# Customers
GET/POST   /api/v1/customers/
GET/PUT    /api/v1/customers/{id}/

# Products
GET/POST   /api/v1/products/
GET/PUT    /api/v1/products/{id}/

# Orders
GET/POST   /api/v1/orders/
POST       /api/v1/orders/{id}/add_item/
POST       /api/v1/orders/{id}/update_status/

# Invoices
GET/POST   /api/v1/invoices/
GET        /api/v1/invoices/overdue/
POST       /api/v1/invoices/{id}/send/

# Payments
GET/POST   /api/v1/payments/
POST       /api/v1/payments/{id}/mark_completed/

# Subscriptions
GET/POST   /api/v1/subscriptions/
POST       /api/v1/subscriptions/{id}/cancel/
POST       /api/v1/subscriptions/{id}/upgrade/
```

## 🔄 Background Tasks

Celery handles various background tasks:

- **Recurring Invoices**: Automatically generate recurring invoices
- **Payment Reminders**: Send overdue payment notifications
- **Subscription Renewals**: Process subscription renewals
- **Usage Tracking**: Monitor subscription usage limits
- **System Maintenance**: Cleanup and health checks

## 📊 Monitoring and Maintenance

### Health Checks

Built-in health check endpoint: `/health/`

### Logs

View application logs:
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f web
docker-compose logs -f celery
```

### Backups

Create database backups:
```bash
./deploy.sh backup
# Or manually:
docker-compose exec db pg_dump -U tidedbu tide > backup.sql
```

### Updates

Update the application:
```bash
git pull origin master
docker-compose pull
docker-compose build --no-cache
docker-compose up -d
docker-compose exec web python tidebilling/manage.py migrate
```

## 🛡️ Security Features

- **HTTPS Enforcement**: Secure communication in production
- **Rate Limiting**: API rate limiting with Redis
- **CORS Protection**: Configurable CORS settings
- **SQL Injection Protection**: Django ORM protection
- **XSS Protection**: Content Security Policy headers
- **CSRF Protection**: Built-in Django CSRF protection
- **Input Validation**: Comprehensive input validation
- **Secure Headers**: Security headers via Nginx

## 🧪 Testing

Run tests:
```bash
docker-compose exec web python tidebilling/manage.py test
```

## 📈 Scaling

For high-traffic deployments:

1. **Database**: Use managed PostgreSQL service
2. **Cache**: Use managed Redis service
3. **Load Balancing**: Add multiple web containers
4. **CDN**: Use CDN for static files
5. **Monitoring**: Add APM tools like Sentry

## 🤝 Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/new-feature`
3. Commit changes: `git commit -am 'Add new feature'`
4. Push to branch: `git push origin feature/new-feature`
5. Submit pull request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

- **Documentation**: Check this README and API docs
- **Issues**: Create GitHub issues for bugs
- **Security**: Email security@tidebilling.com for security issues

## 🗺️ Roadmap

- [ ] Multi-tenant support
- [ ] Advanced analytics dashboard
- [ ] Mobile app API
- [ ] Additional payment gateways
- [ ] Advanced reporting features
- [ ] Multi-currency support
- [ ] Webhook integrations
- [ ] Advanced subscription features

---

**Happy Billing! 🌊💰**
