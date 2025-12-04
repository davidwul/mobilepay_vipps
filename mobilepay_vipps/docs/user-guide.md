# Vipps/MobilePay Payment Integration - User Guide

## Overview

The Vipps/MobilePay Payment Integration module provides comprehensive mobile payment capabilities for Odoo 17 CE, supporting both eCommerce and Point of Sale transactions across Nordic markets.

## Quick Start

### 1. Installation
1. Install the module from Odoo Apps
2. The onboarding wizard will launch automatically
3. Follow the setup steps to configure your payment provider

### 2. Basic Configuration
1. Go to **Accounting → Payment Providers**
2. Create or edit the Vipps/MobilePay provider
3. Enter your API credentials from the merchant portal
4. Configure webhook settings
5. Test the configuration

### 3. First Payment
1. Process a test transaction in your chosen environment
2. Verify webhook notifications are working
3. Check transaction appears correctly in Odoo
4. Switch to production when ready

## Detailed Configuration

### API Credentials
Obtain these from your Vipps/MobilePay merchant portal:
- **Merchant Serial Number**: 6-digit identifier
- **Client ID**: API client identifier  
- **Client Secret**: Secure API secret
- **Subscription Key**: API subscription key

### Webhook Setup
1. **Webhook URL**: Automatically generated as `https://yourdomain.com/payment/vipps/webhook`
2. **Webhook Secret**: Generate a strong secret (minimum 32 characters)
3. Configure the same URL and secret in your merchant portal

### Payment Methods
- **QR Code Payments**: Customers scan QR codes
- **Phone Number Payments**: Send push notifications to customer phones
- **Manual Verification**: For high-value transactions
- **Express Checkout**: One-click payments for returning customers

## eCommerce Integration

### Checkout Configuration
1. Enable Vipps/MobilePay in payment methods
2. Configure payment method display order
3. Customize payment buttons and descriptions
4. Test mobile and desktop checkout flows

### Customer Experience
- **Desktop**: Customer scans QR code with mobile app
- **Mobile**: Automatic redirect to payment app
- **Phone Entry**: Customer enters phone number for push notification

## Point of Sale Integration

### POS Setup
1. Go to **Point of Sale → Configuration**
2. Add Vipps/MobilePay payment methods to your POS
3. Configure timeout settings and verification thresholds
4. Train staff on payment processes

### Payment Flows
1. **QR Code**: Display QR code for customer to scan
2. **Phone Number**: Send payment request to customer's phone
3. **Manual Shop Number**: Customer enters shop number in their app
4. **Manual Verification**: Cashier verifies payment on customer's phone

## Troubleshooting

### Common Issues

#### Payment Not Processing
- Check internet connection
- Verify API credentials are correct
- Ensure webhook is properly configured
- Check customer has sufficient funds

#### QR Code Won't Scan
- Clean the display screen
- Ensure good lighting
- Check for screen damage
- Try generating a new QR code

#### Webhook Issues
- Verify webhook URL is accessible
- Check webhook secret matches
- Ensure HTTPS certificate is valid
- Review webhook logs for errors

### Getting Help
1. Check the troubleshooting section in this documentation
2. Review system logs: **Settings → Technical → Logging**
3. Contact your system administrator
4. Reach out to technical support with detailed error information

## Security and Compliance

### Data Protection
- All sensitive data is encrypted using AES-256
- Webhook signatures prevent tampering
- Audit logs track all payment activities
- GDPR compliance tools included

### Best Practices
- Use strong webhook secrets
- Regularly update API credentials
- Monitor payment success rates
- Train staff on security procedures
- Keep the module updated

## Advanced Features

### Subscription Payments
- Set up recurring billing cycles
- Automatic payment processing
- Failed payment handling
- Customer subscription management

### Analytics and Reporting
- Payment method performance tracking
- Transaction success rate analysis
- Customer payment preferences
- Revenue reporting by payment type

### Custom Integrations
- RESTful API for custom development
- Webhook system for real-time updates
- Extensible payment method framework
- Integration with third-party services

## Support and Resources

### Documentation
- [Onboarding Setup Guide](onboarding-setup-guide.md)
- [API Documentation](api-integration.md)
- [POS User Guide](pos-user-guide.md)
- [Interactive Training Guide](interactive-training-guide.md)

### Getting Support
- Review this documentation first
- Check system logs for error details
- Contact your system administrator
- Provide detailed error information when requesting support

### Community Resources
- Odoo Community Forum
- Module documentation repository
- Best practices guides
- Regular updates and improvements

---

*This guide covers the essential features and configuration options. For advanced customization and development, refer to the API documentation and technical guides.*