# 🌊 Tide Billing

A comprehensive, production-ready billing and subscription management system built with Django, featuring robust API endpoints, automated recurring billing, payment processing, and service management.

## 🚀 Features

### Core Functionality
- **Customer Management**: Complete customer profiles with contacts and billing information
- **Product Catalog**: Products with categories, subcategories, tags, and inventory management
- **Order Processing**: Full order lifecycle from creation to fulfillment
- **Invoice Management**: Automated invoice generation, recurring billing, and payment tracking
- **Payment Recording**: Cash/manual payment recording with refunds that settle back to the invoice
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

- **Backend**: Django 5.2 LTS + Django REST Framework
- **Database**: PostgreSQL 15
- **Cache/Queue**: Redis 7
- **Task Queue**: Celery
- **Web Server**: Nginx + Gunicorn
- **Containerization**: Docker + Docker Compose
- **API Documentation**: OpenAPI/Swagger

## 📋 Prerequisites

- Docker and Docker Compose
- Git
- Domain name (for production)
- SSL certificate (for production)

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
   docker-compose exec web python tidebilling/manage.py setup_roles
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
   docker-compose exec web python tidebilling/manage.py setup_roles
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

# Business Settings
CURRENCY_CODE=USD          # snapshotted onto each order/invoice
TAX_RATE=0.10              # snapshotted; changing it never alters issued invoices
DEFAULT_FROM_EMAIL=noreply@your-domain.com
```

### Payments

The system is **cash-only**: payments are recorded by staff, not charged
through a gateway. The `STRIPE_*` / `PAYPAL_*` settings and the gateway fields
on `Payment` are unused scaffolding kept for a future integration. Adding a
gateway would also require inbound webhooks to reconcile async events.

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
  http://localhost:8000/api/v1/customers/customers/
```

### Key Endpoints

Routes are `/api/v1/<app>/<resource>/`. The app segment is load-bearing: both
`products` and `services` register a `categories` resource, so a flat
`/api/v1/<resource>/` scheme would make one of them unreachable.

```
# Customers
GET/POST   /api/v1/customers/customers/
GET/PUT    /api/v1/customers/customers/{id}/
GET        /api/v1/customers/customers/{id}/contacts/
GET        /api/v1/customers/customers/search/?q=
GET/POST   /api/v1/customers/contacts/

# Products
GET/POST   /api/v1/products/products/
GET/PUT    /api/v1/products/products/{id}/
GET        /api/v1/products/products/low_stock/?threshold=
POST       /api/v1/products/products/{id}/update_stock/
GET/POST   /api/v1/products/categories/
GET/POST   /api/v1/products/subcategories/
GET/POST   /api/v1/products/tags/

# Orders
GET/POST   /api/v1/orders/orders/
POST       /api/v1/orders/orders/{id}/add_item/
POST       /api/v1/orders/orders/{id}/update_status/
GET        /api/v1/orders/orders/{id}/items/
GET/POST   /api/v1/orders/order-items/

# Invoices
GET/POST   /api/v1/invoices/invoices/
GET        /api/v1/invoices/invoices/overdue/
GET        /api/v1/invoices/invoices/due_soon/?days=
POST       /api/v1/invoices/invoices/{id}/send/
POST       /api/v1/invoices/invoices/{id}/add_item/
GET/POST   /api/v1/invoices/invoice-items/

# Payments
GET/POST   /api/v1/payments/payments/
POST       /api/v1/payments/payments/{id}/mark_completed/
POST       /api/v1/payments/payments/{id}/mark_failed/
POST       /api/v1/payments/payments/{id}/create_refund/
GET/POST   /api/v1/payments/refunds/
GET/POST   /api/v1/payments/payment-methods/

# Subscriptions
GET/POST   /api/v1/subscriptions/subscriptions/
POST       /api/v1/subscriptions/subscriptions/{id}/cancel/
POST       /api/v1/subscriptions/subscriptions/{id}/reactivate/
POST       /api/v1/subscriptions/subscriptions/{id}/upgrade/
POST       /api/v1/subscriptions/subscriptions/{id}/add_usage/
GET        /api/v1/subscriptions/subscriptions/expiring_soon/?days=
GET/POST   /api/v1/subscriptions/plans/
GET        /api/v1/subscriptions/plans/active/
GET        /api/v1/subscriptions/changes/          # read-only
GET        /api/v1/subscriptions/usage/            # read-only

# Services
GET/POST   /api/v1/services/requests/
POST       /api/v1/services/requests/{id}/assign/
POST       /api/v1/services/requests/{id}/update_status/
GET/POST   /api/v1/services/services/
GET/POST   /api/v1/services/categories/
GET/POST   /api/v1/services/deliverables/
POST       /api/v1/services/deliverables/{id}/mark_completed/
GET/POST   /api/v1/services/time-logs/
GET/POST   /api/v1/services/feedback/

# Health check (unauthenticated)
GET        /health/
```

### New billing endpoints

```
# Compliance / corrections
POST       /api/v1/invoices/invoices/{id}/cancel/          # records reason in history
POST       /api/v1/invoices/invoices/{id}/credit_note/     # {amount, reason}
GET        /api/v1/invoices/invoices/{id}/history/         # audit trail
GET        /api/v1/invoices/invoices/{id}/pdf/             # PDF download
GET        /api/v1/invoices/invoices/aging/                # AR aging buckets

# Order -> Invoice -> Payment
POST       /api/v1/orders/orders/{id}/generate_invoice/    # idempotent

# Refunds actually settle
POST       /api/v1/payments/payments/{id}/create_refund/   # creates it pending
POST       /api/v1/payments/refunds/{id}/complete/         # settles vs invoice

# Customers
POST       /api/v1/customers/customers/{id}/archive/
POST       /api/v1/customers/customers/{id}/unarchive/
GET        /api/v1/customers/customers/{id}/statement/
DELETE     /api/v1/customers/customers/{id}/               # archives if history exists
```

### Roles

Access is staff-only and role-based. Provision the groups once with
`manage.py setup_roles` (compose and `deploy.sh` run it automatically), then
add each user to a group:

| Role | Read | Create/Edit | Delete |
|------|------|-------------|--------|
| `admin` | yes | yes | yes |
| `billing` | yes | yes | no |
| `readonly` | yes | no | no |

A user in no role group is read-only. Issued invoices cannot be edited or
deleted by anyone — cancel them or issue a credit note.

## ✅ Tests

```bash
# On the host, no services needed (SQLite, eager Celery, locmem email)
python tidebilling/manage.py test --settings=tidebilling.settings_test

# Against the compose PostgreSQL
TEST_DATABASE=postgres python tidebilling/manage.py test --settings=tidebilling.settings_test

# Inside the container
docker compose exec -e TEST_DATABASE=postgres web \
  python tidebilling/manage.py test --settings=tidebilling.settings_test

# A single app or test
python tidebilling/manage.py test orders --settings=tidebilling.settings_test
```

`--settings=tidebilling.settings_test` is required even in the container: the
containers run `ENVIRONMENT=production`, which enables `SECURE_SSL_REDIRECT`,
and API tests would receive 301s.

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
