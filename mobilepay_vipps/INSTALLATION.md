# Vipps/MobilePay Integration - Installation Guide

This guide provides step-by-step instructions for installing and configuring the Vipps/MobilePay payment integration for Odoo.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation Methods](#installation-methods)
3. [Configuration](#configuration)
4. [Testing](#testing)
5. [Production Deployment](#production-deployment)
6. [Troubleshooting](#troubleshooting)

## Prerequisites

### System Requirements

- **Odoo Version**: 17.0 or higher
- **Python**: 3.8 or higher
- **Database**: PostgreSQL 12 or higher
- **Operating System**: Linux (Ubuntu 20.04+ recommended)
- **Memory**: Minimum 4GB RAM (8GB+ recommended for production)
- **Storage**: Minimum 10GB free space

### Python Dependencies

```bash
pip install requests cryptography
```

### Odoo Modules

The following Odoo modules must be installed:
- `base`
- `payment`
- `website_sale` (for eCommerce integration)
- `point_of_sale` (for POS integration)
- `account`
- `sale`

### Vipps/MobilePay Requirements

- Valid Vipps merchant account (Norway) or MobilePay merchant account (Denmark/Finland)
- API credentials (Merchant Serial Number, Client ID, Subscription Key)
- Webhook endpoint accessible from the internet
- SSL certificate for webhook security

## Installation Methods

### Method 1: Odoo Apps Store (Recommended)

1. **Access Odoo Apps**
   - Log in to your Odoo instance as administrator
   - Go to Apps menu
   - Search for "Vipps MobilePay"

2. **Install Module**
   - Click "Install" on the Vipps/MobilePay Payment Integration module
   - Wait for installation to complete
   - The module will be automatically activated

### Method 2: Manual Installation

1. **Download Module**
   ```bash
   # Clone from repository
   git clone https://github.com/waltherB/mobilepay_vipps.git
   
   # Or download and extract ZIP file
   wget https://github.com/waltherB/mobilepay_vipps/archive/main.zip
   unzip main.zip
   ```

2. **Copy to Addons Directory**
   ```bash
   # Copy module to Odoo addons directory
   cp -r payment_vipps_mobilepay /opt/odoo/addons/
   
   # Set proper permissions
   chown -R odoo:odoo /opt/odoo/addons/payment_vipps_mobilepay
   chmod -R 755 /opt/odoo/addons/payment_vipps_mobilepay
   ```

3. **Update Apps List**
   - Restart Odoo service
   - Go to Apps menu in Odoo
   - Click "Update Apps List"
   - Search for "Vipps MobilePay" and install

### Method 3: Deployment Script

1. **Prepare Deployment**
   ```bash
   # Configure deployment
   cp deployment_config_template.json deployment_config.json
   # Edit deployment_config.json with your settings
   ```

2. **Deploy to Environment**
   ```bash
   # Deploy to development
   python deploy.py deploy --environment development
   
   # Deploy to production
   python deploy.py deploy --environment production
   ```

## Configuration

### Step 1: Basic Module Configuration

1. **Access Payment Providers**
   - Go to Accounting → Configuration → Payment Providers
   - Find "Vipps/MobilePay" provider

2. **Enable Provider**
   - Set State to "Enabled"
   - Check "Published" to make it available to customers

### Step 2: API Credentials Configuration

1. **Environment Selection**
   - Choose "Test" for development/testing
   - Choose "Production" for live transactions

2. **Enter Credentials**
   - **Merchant Serial Number**: Your Vipps/MobilePay merchant ID
   - **Client ID**: API client identifier
   - **Subscription Key**: API subscription key
   - **Client Secret**: API client secret (if required)

3. **Webhook Configuration**
   - **Webhook URL**: `https://yourdomain.com/payment/vipps/webhook`
   - **Webhook Secret**: Generate a secure random string (32+ characters)

### Step 3: Feature Configuration

1. **Payment Features**
   - Enable "Manual Capture" if you want to capture payments manually
   - Configure "Payment Flow" (redirect or inline)
   - Set up "Express Checkout" if desired

2. **Customer Profile Collection**
   - Choose which customer data to collect
   - Configure privacy settings
   - Set data retention policies

3. **POS Configuration** (if using Point of Sale)
   - Go to Point of Sale → Configuration → Payment Methods
   - Create new payment method linked to Vipps/MobilePay provider
   - Configure POS-specific settings

### Step 4: Onboarding Wizard

1. **Run Onboarding Wizard**
   - Go to Payment Providers → Vipps/MobilePay
   - Click "Run Onboarding Wizard"

2. **Follow Wizard Steps**
   - Environment setup
   - Credential validation
   - Feature configuration
   - Test transactions
   - Go-live checklist

## Testing

### Step 1: Credential Validation

```bash
# Run credential validation
python -c "
from models.payment_provider import PaymentProvider
provider = PaymentProvider.search([('code', '=', 'vipps_mobilepay')])
result = provider.vipps_validate_credentials()
print('Validation result:', result)
"
```

### Step 2: Test Transactions

1. **eCommerce Test**
   - Create a test product in your online store
   - Go through checkout process
   - Select Vipps/MobilePay as payment method
   - Complete test transaction

2. **POS Test**
   - Open POS interface
   - Create a test sale
   - Select Vipps/MobilePay payment method
   - Test different payment flows (QR, phone, manual)

### Step 3: Webhook Testing

```bash
# Test webhook endpoint
curl -X POST https://yourdomain.com/payment/vipps/webhook \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test_token" \
  -d '{"orderId": "test_order", "transactionInfo": {"status": "RESERVED"}}'
```

### Step 4: Comprehensive Testing

```bash
# Run full test suite
python -m pytest tests/ -v

# Run specific test categories
python -m pytest tests/test_payment_flow.py -v
python -m pytest tests/test_security.py -v
python -m pytest tests/test_pos_integration.py -v
```

## Production Deployment

### Step 1: Production Readiness Validation

```bash
# Run production readiness validation
python run_production_validation.py

# Check specific components
python production_readiness_validator.py
python stress_test_runner.py
python disaster_recovery_tester.py
```

### Step 2: Production Configuration

1. **Update Configuration**
   - Switch to production environment
   - Update API credentials with production values
   - Configure production webhook URL
   - Enable SSL/HTTPS

2. **Security Configuration**
   - Enable firewall
   - Configure access controls
   - Set up monitoring and alerting
   - Enable audit logging

### Step 3: Go-Live Checklist

- [ ] Production credentials configured and validated
- [ ] Webhook endpoint accessible and secure
- [ ] SSL certificate installed and valid
- [ ] Firewall configured
- [ ] Monitoring and alerting set up
- [ ] Backup procedures configured
- [ ] Staff training completed
- [ ] Test transactions successful
- [ ] Documentation reviewed
- [ ] Support contacts established

### Step 4: Deployment

```bash
# Create production deployment package
python deploy.py package --environment production

# Deploy to production
python deploy.py deploy --environment production

# Verify deployment
python deploy.py list
```

## Advanced Configuration

### SSL/HTTPS Setup with Nginx

1. **Install SSL Certificate**
   ```bash
   # Using Let's Encrypt
   sudo certbot --nginx -d yourdomain.com
   ```

2. **Configure Nginx**
   ```nginx
   server {
       listen 443 ssl;
       server_name yourdomain.com;
       
       ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
       ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
       
       location / {
           proxy_pass http://127.0.0.1:8069;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
       
       location /payment/vipps/webhook {
           proxy_pass http://127.0.0.1:8069;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
           
           # Webhook-specific settings
           proxy_read_timeout 30s;
           proxy_connect_timeout 10s;
       }
   }
   ```

### Database Configuration

1. **PostgreSQL Optimization**
   ```sql
   -- Optimize for payment processing
   ALTER SYSTEM SET shared_buffers = '256MB';
   ALTER SYSTEM SET effective_cache_size = '1GB';
   ALTER SYSTEM SET maintenance_work_mem = '64MB';
   ALTER SYSTEM SET checkpoint_completion_target = 0.9;
   ALTER SYSTEM SET wal_buffers = '16MB';
   ALTER SYSTEM SET default_statistics_target = 100;
   
   SELECT pg_reload_conf();
   ```

2. **Backup Configuration**
   ```bash
   # Set up automated backups
   crontab -e
   
   # Add backup job (daily at 2 AM)
   0 2 * * * pg_dump -h localhost -U odoo_user production_db | gzip > /backup/odoo_$(date +\%Y\%m\%d).sql.gz
   ```

### Monitoring Setup

1. **Log Monitoring**
   ```bash
   # Monitor Odoo logs
   tail -f /var/log/odoo/odoo.log | grep -i vipps
   
   # Monitor webhook activity
   tail -f /var/log/nginx/access.log | grep webhook
   ```

2. **Performance Monitoring**
   ```bash
   # Monitor system resources
   htop
   iotop
   
   # Monitor database performance
   sudo -u postgres psql -c "SELECT * FROM pg_stat_activity WHERE datname = 'production_db';"
   ```

## Troubleshooting

### Common Issues

#### 1. Module Installation Fails

**Problem**: Module doesn't appear in Apps list or installation fails

**Solutions**:
```bash
# Check file permissions
ls -la /opt/odoo/addons/payment_vipps_mobilepay/
sudo chown -R odoo:odoo /opt/odoo/addons/payment_vipps_mobilepay/

# Check Odoo logs
tail -f /var/log/odoo/odoo.log

# Update apps list
# Go to Apps → Update Apps List in Odoo interface
```

#### 2. API Credential Validation Fails

**Problem**: "Invalid credentials" or "Connection failed" errors

**Solutions**:
```bash
# Test API connectivity
curl -H "Ocp-Apim-Subscription-Key: YOUR_KEY" \
     -H "client_id: YOUR_CLIENT_ID" \
     https://api.vipps.no/accesstoken/get

# Check firewall settings
sudo ufw status
sudo iptables -L

# Verify credentials in Vipps portal
```

#### 3. Webhook Not Receiving Calls

**Problem**: Payments not updating status automatically

**Solutions**:
```bash
# Test webhook endpoint
curl -X POST https://yourdomain.com/payment/vipps/webhook \
     -H "Content-Type: application/json" \
     -d '{"test": "webhook"}'

# Check SSL certificate
openssl s_client -connect yourdomain.com:443 -servername yourdomain.com

# Verify webhook URL in Vipps portal
# Check Nginx/Apache logs for incoming requests
```

#### 4. POS Integration Issues

**Problem**: POS payment method not working

**Solutions**:
```bash
# Check POS configuration
# Go to Point of Sale → Configuration → Payment Methods
# Verify payment method is linked to Vipps provider

# Clear browser cache and restart POS session
# Check browser console for JavaScript errors
```

#### 5. Performance Issues

**Problem**: Slow payment processing or timeouts

**Solutions**:
```bash
# Increase Odoo workers
# Edit /etc/odoo/odoo.conf
workers = 4
max_cron_threads = 2

# Optimize database
sudo -u postgres psql production_db -c "VACUUM ANALYZE;"

# Check system resources
free -h
df -h
```

### Log Analysis

#### Odoo Logs
```bash
# Payment-related logs
grep -i "vipps\|mobilepay" /var/log/odoo/odoo.log

# Error logs
grep -i "error\|exception" /var/log/odoo/odoo.log | grep -i vipps

# Webhook logs
grep -i "webhook" /var/log/odoo/odoo.log
```

#### System Logs
```bash
# System errors
journalctl -u odoo -f

# Nginx logs
tail -f /var/log/nginx/error.log
tail -f /var/log/nginx/access.log | grep vipps
```

### Getting Help

1. **Documentation**: Check the complete documentation in the `docs/` directory
2. **Test Suite**: Run the comprehensive test suite to identify issues
3. **Validation Tools**: Use the production readiness validation tools
4. **Community**: Check GitHub issues and discussions
5. **Professional Support**: Contact certified Odoo partners for complex deployments

### Support Contacts

- **Technical Issues**: Create issue on GitHub repository
- **Security Concerns**: Email security@yourorg.com
- **Commercial Support**: Contact certified Odoo partners
- **Vipps API Support**: https://developer.vipps.no/
- **MobilePay API Support**: https://developer.mobilepay.dk/

## Maintenance

### Regular Tasks

#### Daily
- Monitor system logs for errors
- Check payment transaction status
- Verify webhook processing

#### Weekly
- Review performance metrics
- Check system resource usage
- Update security patches

#### Monthly
- Run security scans
- Review access logs
- Test backup procedures

#### Quarterly
- Full system health check
- Performance optimization review
- Security audit
- Disaster recovery testing

### Updates and Upgrades

```bash
# Check for module updates
git pull origin main

# Test updates in staging environment
python deploy.py deploy --environment staging

# Deploy to production after testing
python deploy.py deploy --environment production

# Rollback if needed
python deploy.py rollback --environment production
```

This installation guide provides comprehensive instructions for deploying the Vipps/MobilePay integration. For additional help, refer to the documentation in the `docs/` directory or contact support.