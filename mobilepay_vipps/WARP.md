# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

This is a production-ready Odoo 17 CE module providing Vipps/MobilePay payment integration for Nordic countries (Norway, Denmark, Finland, Sweden). The module supports both e-commerce and Point of Sale (POS) payment scenarios with comprehensive security, webhook handling, and GDPR/PCI DSS compliance features.

**Status**: Production-ready (v1.0.2), 100% Odoo 17 CE compatible

## Common Development Commands

### Testing
```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test suites
python -m pytest tests/test_payment_vipps.py -v              # Unit tests
python -m pytest tests/test_security_compliance_comprehensive.py -v  # Security tests
python -m pytest tests/test_pos_payment_flow.py -v          # POS integration tests
python -m pytest tests/test_webhook_security.py -v          # Webhook tests

# Run with coverage
python -m pytest tests/ --cov=. --cov-report=html
```

### Validation & Deployment
```bash
# Validate Odoo 17 compatibility
python3 odoo17_compatibility_audit.py

# Run production readiness validation (comprehensive check)
python3 run_production_validation.py

# Individual validation scripts
python3 production_readiness_validator.py     # System validation
python3 stress_test_runner.py                 # Performance testing
python3 disaster_recovery_tester.py           # Backup/recovery testing

# Deploy to environment
python deploy.py deploy --environment development
python deploy.py deploy --environment production

# Check deployment status
python deploy.py list
```

### Database & Webhook Management
```bash
# Update database schema
python update_database_schema.py

# Diagnose webhook issues
python diagnose_webhook_registration.py

# Check webhook status
python check_webhook_status.py

# Clean up orphaned webhooks
python cleanup_orphaned_webhooks.py

# Test webhook endpoint
python test_webhook_fix.py
```

### Odoo Module Commands
```bash
# Install dependencies
pip install -r requirements.txt

# Update Odoo module (from Odoo root)
./odoo-bin -u mobilepay_vipps -d your_database

# Run Odoo with module (development)
./odoo-bin -d your_database -i mobilepay_vipps --dev all

# Validate module structure
python validate_implementation.py

# Check translations
python validate_translations.py
```

## Architecture Overview

### Core Design Pattern
This module follows **Odoo's MVC architecture** with a payment provider pattern:

1. **Models** (`models/`) - Business logic and data structures
2. **Controllers** (`controllers/`) - HTTP endpoints for webhooks and redirects  
3. **Views** (`views/`) - XML templates for UI and forms

### Key Architectural Components

#### Payment Flow Architecture
```
Customer → Odoo Transaction → Vipps API Client → Vipps/MobilePay API
                ↓                      ↓
         Webhook Handler ← Vipps Webhook → Payment Status Update
```

**Critical Design Decisions:**
- **Idempotent Operations**: Every payment operation uses idempotency keys to prevent duplicate transactions
- **Webhook-Driven Status**: Payment states are primarily updated via webhooks (not polling)
- **Per-Transaction Webhooks**: Each payment transaction registers its own webhook for isolation
- **Token Management**: Access tokens are automatically refreshed with 5-minute expiry buffer
- **Context-Aware Capture**: Automatic capture for POS, manual for e-commerce

#### Model Hierarchy & Responsibilities

**`payment_provider.py`** (PaymentProvider)
- Extends `payment.provider` - Odoo's base payment provider model
- Configuration management (credentials, environment, features)
- Access token lifecycle management
- API client initialization
- Webhook URL generation and validation
- Credential encryption/decryption

**`payment_transaction.py`** (PaymentTransaction)  
- Extends `payment.transaction` - Odoo's payment transaction model
- Payment creation and processing (`_send_payment_request`)
- Webhook notification handling (`_process_notification_data`)
- State management (authorized → captured/cancelled)
- QR code generation for POS payments
- Profile data collection and customer record updates

**`vipps_api_client.py`** (VippsAPIClient)
- Centralized API communication layer
- Automatic token refresh and retry logic
- Circuit breaker pattern for API failures
- Rate limiting (100 calls/minute)
- Error handling with detailed exceptions
- Idempotency key management

**`vipps_webhook_security.py`** (PaymentProviderWebhookSecurity)
- HMAC signature validation for webhook authenticity
- IP address whitelisting for Vipps servers
- Replay attack prevention with timestamps
- Per-provider webhook secrets

#### Controller Architecture

**`main.py`** (VippsController)
- `/payment/vipps/webhook` - Receives payment status updates from Vipps
- `/payment/vipps/redirect/<tx_id>` - Handles customer redirects from Vipps
- `/payment/vipps/return` - Success/failure return endpoints
- Webhook signature validation on every request
- Transaction state updates based on webhook events

**`pos_payment.py`** (VippsPosController)
- POS-specific payment endpoints
- QR code generation for customer scanning
- Manual shop number verification flow
- Real-time payment status checking

### Security Architecture

**Multi-Layer Security:**
1. **Credential Encryption**: All sensitive credentials encrypted at rest using `cryptography` library
2. **Webhook Validation**: HMAC-SHA256 signature verification + IP whitelisting
3. **Replay Prevention**: Timestamp validation (5-minute window) + duplicate detection
4. **TLS/HTTPS**: Required for all webhook endpoints
5. **Access Controls**: Group-based field visibility (`base.group_system`)

**Compliance Features:**
- **GDPR**: Data retention policies, explicit consent flows, customer data management
- **PCI DSS**: No card data storage, tokenized payments, audit logging

### Data Flow: E-Commerce Payment

1. Customer initiates checkout → Odoo creates `payment.transaction`
2. Transaction calls `_send_payment_request()` → Creates Vipps payment via API
3. Customer redirects to Vipps → Completes authentication in Vipps app
4. Vipps sends webhook → Controller validates signature → Updates transaction state
5. Transaction state changes → Triggers Odoo workflow (invoice, order confirmation)

### Data Flow: Webhook Processing

1. Vipps sends POST to `/payment/vipps/webhook`
2. Controller validates HMAC signature and timestamp
3. Extract transaction reference from webhook payload
4. Find transaction: `payment.transaction.search([('vipps_payment_reference', '=', ref)])`
5. Call `transaction._process_notification_data(webhook_data)`
6. Transaction updates state using `_set_authorized()`, `_set_done()`, `_set_canceled()`
7. Odoo triggers downstream actions (order confirmation, invoice generation)

## Module Structure & Key Files

### Critical Files for Payment Logic
- `models/payment_provider.py` - Provider configuration, credentials, token management
- `models/payment_transaction.py` - Payment creation, state management, webhook processing
- `models/vipps_api_client.py` - API communication, error handling, retries
- `controllers/main.py` - Webhook endpoint, signature validation, redirect handling

### Security & Validation
- `models/vipps_webhook_security.py` - HMAC validation, IP filtering, replay prevention
- `models/vipps_security.py` - Credential encryption, security features
- `tests/test_webhook_security.py` - Webhook security test suite
- `tests/test_security_compliance_comprehensive.py` - GDPR/PCI DSS tests

### Configuration & Setup
- `__manifest__.py` - Module metadata, dependencies, version
- `data/payment_method_data.xml` - Default payment method configuration
- `views/payment_provider_views.xml` - Provider configuration UI
- `models/vipps_onboarding_wizard.py` - Setup wizard for initial configuration

### Validation & Deployment
- `odoo17_compatibility_audit.py` - Validates Odoo 17 API compatibility
- `production_readiness_validator.py` - System readiness checks
- `run_production_validation.py` - Orchestrates all validation suites
- `deploy.py` - Deployment automation script

## Important Implementation Details

### Odoo 17 Compatibility
This module is **specifically built for Odoo 17 CE**:
- Uses modern `_process_notification_data()` for webhooks (not deprecated `_handle_notification_data`)
- Implements required provider methods: `_get_supported_currencies()`, `_get_supported_countries()`, `_get_default_payment_method_codes()`
- JavaScript uses `/** @odoo-module **/` decorator (not old module system)
- XML views avoid deprecated `attrs` syntax

### Webhook Registration Pattern
**Important**: The module uses **per-payment webhooks** (not global provider webhooks):
- Each payment transaction registers its own webhook via Webhooks API v1
- Webhook URL format: `https://domain.com/payment/vipps/webhook`
- Transaction reference embedded in webhook payload (not URL path)
- This allows proper transaction isolation and concurrent payment handling

### Credential Management
**Always use decrypted accessors**:
```python
# DON'T access encrypted fields directly
self.provider.vipps_client_secret_encrypted  # ❌ This is encrypted

# DO use decrypted properties
self.provider.vipps_client_secret_decrypted  # ✅ Returns plaintext
```

The `vipps_security.py` model provides automatic encryption/decryption via computed fields.

### API Client Usage Pattern
```python
# Always get client from transaction or provider
api_client = transaction._get_vipps_api_client()

# API client handles:
# - Token refresh (automatic when expired)
# - Idempotency keys (auto-generated)
# - Retry logic (3 attempts with exponential backoff)
# - Error handling (raises VippsAPIException)
```

### Environment-Specific Endpoints
```python
# Test environment
test_api_base = "https://apitest.vipps.no/epayment/v1"
test_token_url = "https://apitest.vipps.no/accesstoken/get"

# Production environment  
prod_api_base = "https://api.vipps.no/epayment/v1"
prod_token_url = "https://api.vipps.no/accesstoken/get"
```

## Testing Strategy

### Test Suite Organization
- **Unit Tests**: `test_payment_vipps.py`, `test_api_client_comprehensive.py`
- **Integration Tests**: `test_ecommerce_payment_flow.py`, `test_pos_payment_flow.py`
- **Security Tests**: `test_webhook_security.py`, `test_penetration_testing.py`
- **Compliance Tests**: `test_gdpr_compliance.py`, `test_security_compliance_comprehensive.py`
- **Production Tests**: `test_production_*.py` (system, performance, disaster recovery)

### Mock vs Real API
Tests use mocks by default (`unittest.mock`). For real API testing:
1. Set test credentials in provider configuration
2. Use `vipps_environment = 'test'`
3. Tests will hit real Vipps test API endpoints

## Common Development Patterns

### Creating a Payment Transaction
```python
# E-commerce flow
transaction = env['payment.transaction'].create({
    'provider_id': vipps_provider.id,
    'amount': 100.0,
    'currency_id': currency_nok.id,
    'partner_id': customer.id,
    'reference': 'ORDER-12345',
})
transaction._send_payment_request()  # Returns {'url': 'https://...', 'reference': '...'}
```

### Processing Webhook Data
```python
# Controller receives webhook
webhook_data = {
    'name': 'epayments.payment.authorized.v1',
    'reference': 'vipps-payment-ref-12345',
    'pspReference': 'psp-ref-67890',
    'amount': {'value': 10000, 'currency': 'NOK'},
}

# Find and update transaction
transaction = env['payment.transaction'].search([
    ('vipps_payment_reference', '=', webhook_data['reference'])
])
transaction._process_notification_data(webhook_data)
```

### Adding New API Endpoints
When adding new Vipps API integrations:
1. Add method to `VippsAPIClient` in `vipps_api_client.py`
2. Use `_make_api_request()` for standard calls
3. Include proper error handling with `VippsAPIException`
4. Add idempotency key for POST/PUT operations
5. Write unit tests with mocked responses

## Known Limitations & Gotchas

1. **POS Module Dependency**: POS integration is optional. Models conditionally import POS dependencies.
2. **Webhook IP Whitelisting**: Vipps IPs change occasionally - update `vipps_webhook_security.py` if webhooks fail validation
3. **Token Expiry**: Access tokens expire after 1 hour. Client auto-refreshes but be aware of timing in long-running operations.
4. **Idempotency Keys**: Are single-use per API call. Never reuse an idempotency key for different operations.
5. **Amount Format**: Vipps expects amounts in øre/cents (e.g., 100 NOK = 10000). API client handles conversion.

## Troubleshooting

### Webhook Not Receiving Updates
```bash
# Check webhook registration
python diagnose_webhook_registration.py

# Verify webhook secret matches
python check_webhook_secret.py

# Test webhook endpoint directly
curl -X POST https://your-domain.com/payment/vipps/webhook \
  -H "Content-Type: application/json" \
  -d '{"test": "webhook"}'
```

### API Credential Errors
```bash
# Validate credentials
python check_provider_config.py

# Check token generation
# Look for "Successfully refreshed access token" in logs
tail -f /var/log/odoo/odoo.log | grep -i vipps
```

### Payment State Not Updating
Check Odoo logs for:
- `vipps_webhook_security` - Signature validation failures
- `payment.transaction` - Transaction state transition errors
- `vipps.api.client` - API communication errors

## Module Dependencies

**Required Odoo Modules:**
- `base` - Core Odoo framework
- `payment` - Odoo payment provider framework
- `website_sale` - E-commerce integration

**Optional Odoo Modules:**
- `point_of_sale` - For POS payment features
- `account` - For invoice integration
- `sale` - For sales order integration

**Python Dependencies (requirements.txt):**
- `requests>=2.31.0` - HTTP client for API calls
- `cryptography>=41.0.0` - Credential encryption
- `qrcode[pil]>=7.4.0` - QR code generation for POS
- `phonenumbers>=8.13.0` - Phone number validation

## Code Style & Conventions

- **Python**: Follow PEP 8, use type hints where appropriate
- **Logging**: Use module-level logger: `_logger = logging.getLogger(__name__)`
- **Error Handling**: Raise `UserError` for user-facing errors, `ValidationError` for data validation, `VippsAPIException` for API errors
- **Docstrings**: Use triple-quoted strings for all public methods
- **Field Naming**: Prefix all custom fields with `vipps_` to avoid conflicts
- **API Methods**: Prefix internal methods with `_` (e.g., `_get_access_token()`)

## Version Compatibility

| Odoo Version | Module Version | Status |
|--------------|----------------|--------|
| 17.0 CE      | 1.0.0+        | ✅ Full support |
| 16.0 CE      | -             | ❌ Not supported |
| 15.0 CE      | -             | ❌ Not supported |

**Python**: 3.8+  
**PostgreSQL**: 12+
