# Vipps/MobilePay User Manual

## Table of Contents
1. [Getting Started](#getting-started)
2. [Online Payment Configuration](#online-payment-configuration)
3. [Managing Payment Transactions](#managing-payment-transactions)
4. [Customer Profile Integration](#customer-profile-integration)
5. [Reporting and Analytics](#reporting-and-analytics)
6. [Troubleshooting](#troubleshooting)
7. [FAQ](#faq)

## Getting Started

### Overview
The Vipps/MobilePay integration allows you to accept payments from customers using their mobile phones. This guide will help you configure and manage payments for your online store.

### Prerequisites
Before you begin, ensure you have:
- An active Vipps merchant account (for Norwegian customers)
- An active MobilePay merchant account (for Danish customers)
- API credentials from your payment provider
- Administrator access to your Odoo system

### Initial Setup
1. **Install the Module**
   - Go to **Apps** in your Odoo dashboard
   - Search for "Vipps" or "MobilePay"
   - Click **Install** on the Vipps/MobilePay Payment module

2. **Access Payment Configuration**
   - Navigate to **Accounting → Configuration → Payment Providers**
   - Look for the Vipps/MobilePay provider in the list

## Online Payment Configuration

### Basic Configuration

#### Step 1: Enable the Payment Provider
1. Go to **Accounting → Configuration → Payment Providers**
2. Find "Vipps/MobilePay" and click to open
3. Set the **State** to "Enabled"
4. Choose your **Environment**:
   - **Test**: For testing and development
   - **Production**: For live transactions

#### Step 2: Configure API Credentials
1. In the payment provider form, fill in:
   - **Merchant Serial Number**: Your 6-digit merchant number
   - **Client ID**: Your API client identifier
   - **Client Secret**: Your API client secret (keep this secure!)
   - **Subscription Key**: Your API subscription key

2. **Save** the configuration

#### Step 3: Configure Webhook Settings
1. In the **Webhook** section:
   - **Webhook URL**: This is automatically generated
   - **Webhook Secret**: Enter a strong secret key (minimum 32 characters)
   - Copy the webhook URL to configure in your Vipps/MobilePay merchant portal

2. **Test the webhook** by clicking "Test Webhook Connection"

### Advanced Configuration

#### Payment Methods
Configure which payment methods to offer:

1. **QR Code Payments**
   - Enable "QR Code Payments"
   - Set QR code timeout (default: 5 minutes)
   - Choose QR code size and format

2. **Phone Number Payments**
   - Enable "Phone Number Payments"
   - Set phone number validation rules
   - Configure SMS notification settings

3. **Express Checkout**
   - Enable for faster checkout experience
   - Configure button appearance and placement

#### Customer Experience Settings
1. **Payment Page Customization**
   - Upload your logo
   - Set brand colors
   - Customize payment messages

2. **Language Settings**
   - Choose default language (Norwegian, Danish, English)
   - Enable automatic language detection

3. **Mobile Optimization**
   - Enable mobile-optimized payment flow
   - Configure mobile app deep linking

### Testing Your Configuration

#### Test Mode Setup
1. Ensure **Environment** is set to "Test"
2. Use test credentials provided by Vipps/MobilePay
3. Test phone numbers:
   - Norway: +47 99999999
   - Denmark: +45 12345678

#### Performing Test Transactions
1. Go to your website's checkout page
2. Select Vipps/MobilePay as payment method
3. Use test phone number
4. Complete payment in test app
5. Verify transaction appears in Odoo

## Managing Payment Transactions

### Viewing Transactions
1. Go to **Accounting → Customers → Payments**
2. Filter by "Vipps" or "MobilePay" to see relevant transactions
3. Click on any transaction to view details

### Transaction Statuses
- **Draft**: Transaction created but not yet processed
- **Pending**: Waiting for customer to complete payment
- **Authorized**: Payment authorized but not captured
- **Done**: Payment successfully completed
- **Cancelled**: Payment cancelled by customer or system
- **Error**: Payment failed due to error

### Managing Pending Payments
1. **View Pending Payments**
   - Go to **Accounting → Customers → Payments**
   - Filter by Status = "Pending"

2. **Actions for Pending Payments**
   - **Cancel**: Cancel the payment request
   - **Resend**: Send new payment request to customer
   - **Manual Capture**: Capture authorized payment manually

### Refund Processing
1. **Full Refunds**
   - Open the completed transaction
   - Click **Refund** button
   - Confirm the refund amount
   - Add refund reason (optional)

2. **Partial Refunds**
   - Open the completed transaction
   - Click **Partial Refund**
   - Enter refund amount
   - Add refund reason
   - Click **Process Refund**

### Reconciliation
1. **Automatic Reconciliation**
   - Most payments reconcile automatically
   - Check **Accounting → Dashboard** for unreconciled items

2. **Manual Reconciliation**
   - Go to **Accounting → Reconciliation**
   - Match payments with bank statements
   - Resolve any discrepancies

## Customer Profile Integration

### Vipps Profile Data
When customers pay with Vipps, you can optionally collect:
- Name and contact information
- Shipping address
- Age verification (for age-restricted products)

### Configuration
1. **Enable Profile Integration**
   - Go to payment provider configuration
   - Enable "Collect Customer Profile"
   - Select data scopes to collect

2. **Privacy Settings**
   - Configure data retention period
   - Set up consent management
   - Enable GDPR compliance features

### Using Profile Data
1. **Customer Records**
   - Profile data automatically creates/updates customer records
   - View in **Sales → Customers**

2. **Order Processing**
   - Shipping addresses auto-populate
   - Customer information pre-filled for future orders

## Reporting and Analytics

### Payment Reports
1. **Transaction Summary**
   - Go to **Accounting → Reporting → Payment Transactions**
   - Filter by date range and payment method
   - Export to Excel/PDF

2. **Revenue Analysis**
   - View payment trends over time
   - Compare different payment methods
   - Analyze customer payment preferences

### Key Metrics to Monitor
- **Conversion Rate**: Percentage of successful payments
- **Average Transaction Value**: Mean payment amount
- **Payment Method Usage**: Distribution of payment types
- **Failed Payment Rate**: Percentage of failed transactions

### Custom Reports
1. **Create Custom Views**
   - Go to **Settings → Technical → User Interface → Views**
   - Create custom payment reports
   - Add specific filters and groupings

2. **Dashboard Widgets**
   - Add payment KPIs to your dashboard
   - Monitor real-time payment activity
   - Set up alerts for unusual activity

## Troubleshooting

### Common Issues

#### Payment Not Completing
**Symptoms**: Customer completes payment but order remains unpaid

**Solutions**:
1. Check webhook configuration
2. Verify webhook URL is accessible
3. Check webhook logs for errors
4. Manually sync payment status

#### Webhook Errors
**Symptoms**: Webhook validation failures in logs

**Solutions**:
1. Verify webhook secret matches
2. Check webhook URL format
3. Ensure HTTPS is properly configured
4. Test webhook endpoint manually

#### Customer Can't Complete Payment
**Symptoms**: Customer reports payment app not opening

**Solutions**:
1. Verify customer has Vipps/MobilePay app installed
2. Check phone number format
3. Ensure customer has sufficient funds
4. Try alternative payment method

### Error Messages

#### "Invalid Merchant Configuration"
- Check API credentials
- Verify merchant account is active
- Contact Vipps/MobilePay support

#### "Webhook Signature Validation Failed"
- Verify webhook secret
- Check webhook URL configuration
- Review webhook logs

#### "Payment Timeout"
- Check timeout settings
- Verify customer received payment request
- Consider extending timeout period

### Getting Help
1. **Check Logs**
   - Go to **Settings → Technical → Logging**
   - Filter by "vipps" or "mobilepay"
   - Review error messages

2. **Contact Support**
   - Email: support@yourcompany.com
   - Include error messages and transaction IDs
   - Provide steps to reproduce issue

## FAQ

### General Questions

**Q: Which countries are supported?**
A: Currently Norway (Vipps) and Denmark (MobilePay). More countries may be added in future versions.

**Q: What are the transaction fees?**
A: Fees are set by Vipps/MobilePay and vary by merchant agreement. Check with your payment provider for current rates.

**Q: Can I use both Vipps and MobilePay simultaneously?**
A: Yes, you can configure both payment methods and customers will see the appropriate option based on their location.

### Technical Questions

**Q: How long do payments take to process?**
A: Most payments are processed instantly. Bank transfers may take 1-2 business days to appear in your account.

**Q: Can I customize the payment page?**
A: Yes, you can customize colors, logos, and messages in the payment provider configuration.

**Q: Is the integration PCI compliant?**
A: Yes, the integration follows PCI DSS requirements. No sensitive card data is stored in Odoo.

### Business Questions

**Q: Can I offer installment payments?**
A: This depends on your merchant agreement with Vipps/MobilePay. Contact them for installment options.

**Q: How do I handle disputes?**
A: Disputes are managed through your Vipps/MobilePay merchant portal. The Odoo integration will reflect dispute status changes.

**Q: Can I set minimum/maximum payment amounts?**
A: Yes, configure these limits in the payment provider settings.

### Troubleshooting Questions

**Q: Why are some payments showing as pending?**
A: This usually indicates a webhook delivery issue. Check your webhook configuration and logs.

**Q: How do I test the integration?**
A: Use the test environment with provided test credentials and phone numbers.

**Q: What should I do if payments stop working?**
A: Check your API credentials, webhook configuration, and contact support if issues persist.

---

## Need More Help?

### Resources
- **Documentation**: [Complete user documentation](README.md)
- **Community Forum**: User discussions and support
- **Developer Documentation**: [API Integration Guide](api-integration.md)

### Support Channels
- **Email Support**: support@yourcompany.com
- **Live Chat**: Available during business hours
- **Phone Support**: +47 12345678 (Norway), +45 12345678 (Denmark)

### Training
- **Webinar Sessions**: Monthly training webinars
- **On-site Training**: Available for enterprise customers
- **Certification Program**: Become a certified Vipps/MobilePay specialist

---

*This user manual is regularly updated. Last updated: [Current Date]*