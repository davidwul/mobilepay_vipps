# Onboarding Wizard - Setup Guide

## Table of Contents
1. [Overview](#overview)
2. [Pre-Setup Requirements](#pre-setup-requirements)
3. [Step-by-Step Onboarding](#step-by-step-onboarding)
4. [Configuration Validation](#configuration-validation)
5. [Testing Your Setup](#testing-your-setup)
6. [Going Live](#going-live)
7. [Post-Setup Tasks](#post-setup-tasks)
8. [Troubleshooting](#troubleshooting)

## Overview

The Vipps/MobilePay onboarding wizard guides you through the complete setup process, from initial configuration to going live with payments. This step-by-step guide ensures you don't miss any critical configuration steps.

### What the Wizard Covers
- ✅ Payment provider setup
- ✅ API credential configuration
- ✅ Webhook endpoint setup
- ✅ Payment method configuration
- ✅ Security settings
- ✅ Testing and validation
- ✅ Go-live checklist

### Estimated Time
- **Basic Setup**: 15-20 minutes
- **Complete Configuration**: 30-45 minutes
- **Testing and Validation**: 15-30 minutes

## Pre-Setup Requirements

### Before Starting the Wizard

#### 1. Merchant Account Setup
**For Vipps (Norway)**:
- ✅ Active Vipps merchant account
- ✅ Completed merchant onboarding with Vipps
- ✅ Received API credentials from Vipps

**For MobilePay (Denmark)**:
- ✅ Active MobilePay merchant account
- ✅ Completed merchant onboarding with MobilePay
- ✅ Received API credentials from MobilePay

#### 2. Technical Requirements
- ✅ Odoo 17.0 CE or higher
- ✅ SSL certificate installed (HTTPS required)
- ✅ Internet connectivity
- ✅ Administrator access to Odoo

#### 3. Information You'll Need
Gather this information before starting:

**API Credentials**:
- Merchant Serial Number (6 digits)
- Client ID
- Client Secret
- Subscription Key (Ocp-Apim-Subscription-Key)

**Business Information**:
- Company name
- Business registration number
- Contact email
- Support phone number

**Technical Information**:
- Your website domain
- Webhook endpoint URL (auto-generated)
- Preferred timeout settings

## Step-by-Step Onboarding

### Starting the Wizard

1. **Access the Wizard**
   - Go to **Apps** → Search "Vipps"
   - Click **Install** on the Vipps/MobilePay module
   - The onboarding wizard will start automatically
   - Or go to **Accounting** → **Configuration** → **Payment Providers** → **Configure Vipps/MobilePay**

2. **Welcome Screen**
   - Read the welcome message
   - Review the setup checklist
   - Click **Start Setup** to begin

### Step 1: Choose Your Market

**Select Your Primary Market**:
- 🇳🇴 **Norway (Vipps)**: For Norwegian customers
- 🇩🇰 **Denmark (MobilePay)**: For Danish customers
- 🌍 **Both Markets**: If you serve both countries

**Configuration Impact**:
- Determines default currency (NOK/DKK)
- Sets appropriate API endpoints
- Configures country-specific features

**Click Next** to continue.

### Step 2: Environment Selection

**Choose Your Environment**:
- 🧪 **Test Environment**: For development and testing
  - Use test API credentials
  - No real money transactions
  - Safe for experimentation
- 🚀 **Production Environment**: For live transactions
  - Use production API credentials
  - Real money transactions
  - Customer-facing payments

**Recommendation**: Start with Test Environment, then switch to Production after testing.

**Click Next** to continue.

### Step 3: API Credentials Configuration

**Enter Your API Credentials**:

1. **Merchant Serial Number**
   - Enter your 6-digit merchant number
   - Example: `123456`
   - ❓ Where to find: Vipps/MobilePay merchant portal

2. **Client ID**
   - Enter your API client identifier
   - Example: `your-client-id-12345`
   - ❓ Where to find: Developer section of merchant portal

3. **Client Secret**
   - Enter your API client secret
   - ⚠️ Keep this secure and confidential
   - Example: `your-client-secret-abcdef123456`

4. **Subscription Key**
   - Enter your API subscription key
   - Example: `your-subscription-key-xyz789`
   - ❓ Also called: Ocp-Apim-Subscription-Key

**Validation**:
- The wizard will test your credentials
- ✅ Green checkmark = Valid credentials
- ❌ Red X = Invalid credentials (check and retry)

**Click Next** after validation succeeds.

### Step 4: Webhook Configuration

**Webhook Setup**:
The webhook allows real-time payment updates.

1. **Webhook URL** (Auto-generated)
   - URL: `https://yourdomain.com/payment/vipps/webhook`
   - ✅ This is automatically generated
   - 📋 Copy this URL for the next step

2. **Webhook Secret**
   - Enter a strong secret (minimum 32 characters)
   - Example: `your-webhook-secret-12345678901234567890123456789012`
   - 🔐 This ensures webhook security

3. **Configure in Merchant Portal**
   - Open your Vipps/MobilePay merchant portal
   - Navigate to webhook settings
   - Paste the webhook URL
   - Save the configuration

**Test Webhook**:
- Click **Test Webhook** button
- ✅ Success = Webhook is working
- ❌ Failure = Check URL and secret

**Click Next** after webhook test passes.

### Step 5: Payment Methods Configuration

**Select Payment Methods to Enable**:

1. **QR Code Payments** ✅ Recommended
   - Customer scans QR code with their phone
   - Fast and convenient
   - **Timeout**: 300 seconds (5 minutes)

2. **Phone Number Payments** ✅ Recommended
   - Customer enters phone number
   - Payment request sent to phone
   - **Timeout**: 300 seconds (5 minutes)

3. **Express Checkout** (Optional)
   - One-click payments for returning customers
   - Requires customer consent
   - **Auto-confirm**: Yes/No

4. **Manual Verification** (Optional)
   - For high-value transactions
   - Staff verification required
   - **Threshold**: 1000 NOK/DKK

**Advanced Settings**:
- **Auto-capture**: Automatically capture authorized payments
- **Partial refunds**: Allow partial refund processing
- **Receipt delivery**: Email/SMS receipt options

**Click Next** to continue.

### Step 6: Security Configuration

**Security Settings**:

1. **Data Encryption**
   - ✅ Encrypt sensitive data (Recommended)
   - Choose encryption method: AES-256

2. **Access Control**
   - Set user permissions for payment management
   - Configure role-based access

3. **Audit Logging**
   - ✅ Enable security audit logging (Recommended)
   - Log all payment-related activities

4. **GDPR Compliance**
   - ✅ Enable GDPR compliance features (Required for EU)
   - Configure data retention policies
   - Set up consent management

**Click Next** to continue.

### Step 7: Business Information

**Company Details**:

1. **Business Information**
   - Company name: (Auto-filled from Odoo)
   - Registration number: Enter your business registration
   - VAT number: Enter if applicable

2. **Contact Information**
   - Support email: Enter customer support email
   - Support phone: Enter customer support phone
   - Website: (Auto-filled from Odoo)

3. **Branding** (Optional)
   - Upload company logo
   - Set brand colors
   - Customize payment messages

**Click Next** to continue.

### Step 8: Review Configuration

**Configuration Summary**:
Review all your settings:

- ✅ **Market**: Norway/Denmark/Both
- ✅ **Environment**: Test/Production
- ✅ **API Credentials**: Validated
- ✅ **Webhook**: Configured and tested
- ✅ **Payment Methods**: Selected methods
- ✅ **Security**: Configured
- ✅ **Business Info**: Complete

**Make Changes**:
- Click **Back** to modify any settings
- Click **Edit** next to specific sections

**Finalize Setup**:
- Click **Complete Setup** when satisfied

## Configuration Validation

### Automatic Validation Checks

The wizard performs these validation checks:

1. **API Connectivity** ✅
   - Tests connection to Vipps/MobilePay APIs
   - Validates API credentials
   - Checks API rate limits

2. **Webhook Functionality** ✅
   - Tests webhook endpoint accessibility
   - Validates webhook signature
   - Checks HTTPS configuration

3. **Security Configuration** ✅
   - Verifies encryption settings
   - Checks access control configuration
   - Validates security policies

4. **Integration Points** ✅
   - Tests Odoo module integration
   - Validates database configuration
   - Checks required dependencies

### Manual Validation Steps

After wizard completion:

1. **Test API Calls**
   ```bash
   # Test authentication
   curl -X POST https://apitest.vipps.no/accesstoken/get \
     -H "client_id: your-client-id" \
     -H "client_secret: your-client-secret" \
     -H "Ocp-Apim-Subscription-Key: your-subscription-key"
   ```

2. **Verify Webhook**
   - Send test webhook from merchant portal
   - Check Odoo logs for webhook receipt
   - Verify signature validation

3. **Check Database**
   - Verify payment provider record created
   - Check configuration values stored
   - Confirm encryption is working

## Testing Your Setup

### Test Environment Testing

1. **Create Test Transaction**
   - Go to your website checkout
   - Add items to cart
   - Select Vipps/MobilePay payment
   - Use test phone number: +47 99999999 (Norway) or +45 12345678 (Denmark)

2. **Test Payment Flow**
   - Complete payment in test app
   - Verify transaction appears in Odoo
   - Check payment status updates
   - Confirm webhook delivery

3. **Test Different Scenarios**
   - Successful payment
   - Cancelled payment
   - Failed payment
   - Timeout scenario
   - Refund processing

### POS Testing (if applicable)

1. **POS Configuration**
   - Configure POS payment methods
   - Test QR code generation
   - Test phone number payments
   - Test manual verification

2. **POS Transaction Testing**
   - Create test sale
   - Process Vipps/MobilePay payment
   - Verify receipt generation
   - Test refund functionality

### Integration Testing

1. **E-commerce Integration**
   - Test checkout flow
   - Verify order processing
   - Check inventory updates
   - Test customer notifications

2. **Accounting Integration**
   - Verify payment recording
   - Check account reconciliation
   - Test reporting functionality
   - Validate tax calculations

## Going Live

### Pre-Production Checklist

Before switching to production:

- ✅ All tests completed successfully
- ✅ Production API credentials obtained
- ✅ Webhook configured in production merchant portal
- ✅ SSL certificate valid and working
- ✅ Staff training completed
- ✅ Support procedures documented
- ✅ Backup and recovery tested

### Switching to Production

1. **Update Environment**
   - Go to payment provider configuration
   - Change environment from "Test" to "Production"
   - Update API credentials to production values

2. **Update Webhook**
   - Configure production webhook URL in merchant portal
   - Test webhook with production credentials
   - Verify signature validation

3. **Final Testing**
   - Process small test transaction
   - Verify real money handling
   - Check all integrations working

### Go-Live Monitoring

**First 24 Hours**:
- Monitor all transactions closely
- Check for any error messages
- Verify webhook deliveries
- Monitor customer feedback

**First Week**:
- Review transaction success rates
- Check for any integration issues
- Monitor system performance
- Gather user feedback

## Post-Setup Tasks

### User Training

1. **Administrator Training**
   - Payment provider management
   - Transaction monitoring
   - Refund processing
   - Troubleshooting procedures

2. **Cashier Training** (for POS)
   - Payment processing procedures
   - Customer assistance
   - Error handling
   - Daily operations

3. **Customer Service Training**
   - Common customer questions
   - Payment troubleshooting
   - Refund procedures
   - Escalation processes

### Ongoing Maintenance

1. **Regular Monitoring**
   - Daily transaction review
   - Weekly performance reports
   - Monthly security audits
   - Quarterly configuration review

2. **Updates and Maintenance**
   - Keep module updated
   - Monitor API changes
   - Update documentation
   - Review security settings

3. **Performance Optimization**
   - Monitor transaction speeds
   - Optimize webhook processing
   - Review timeout settings
   - Analyze customer feedback

## Troubleshooting

### Common Setup Issues

#### Issue: API Credentials Invalid
**Symptoms**: Credential validation fails during setup

**Solutions**:
1. Double-check credentials in merchant portal
2. Ensure using correct environment (test/production)
3. Verify merchant account is active
4. Contact Vipps/MobilePay support

#### Issue: Webhook Test Fails
**Symptoms**: Webhook validation fails during setup

**Solutions**:
1. Verify HTTPS is properly configured
2. Check webhook URL is accessible from internet
3. Ensure webhook secret matches
4. Check firewall settings

#### Issue: Module Installation Fails
**Symptoms**: Error during module installation

**Solutions**:
1. Check Odoo version compatibility
2. Verify all dependencies installed
3. Check database permissions
4. Review installation logs

### Getting Help During Setup

1. **Built-in Help**
   - Click ❓ icons for context help
   - Use "Help" button in wizard
   - Check tooltips for guidance

2. **Documentation**
   - Review technical documentation
   - Check API documentation
   - Read troubleshooting guides

3. **Support Channels**
   - Email: support@yourcompany.com
   - Live chat: Available during setup
   - Phone: Emergency support line

### Support Information Collection

If you need to contact support, collect:
- Odoo version and module version
- Environment (test/production)
- Error messages and screenshots
- Steps to reproduce issue
- Merchant serial number (for verification)

---

## Congratulations! 🎉

You've successfully completed the Vipps/MobilePay onboarding process. Your payment integration is now ready to accept mobile payments from customers.

### Next Steps
1. Train your staff on the new payment methods
2. Update your website to promote mobile payment options
3. Monitor transactions and gather customer feedback
4. Consider additional features like subscription payments

### Resources
- **User Manual**: Complete guide for daily operations
- **POS Guide**: Specific instructions for cashiers
- **API Documentation**: Technical integration details
- **Support Portal**: Help and troubleshooting resources

*Welcome to the world of mobile payments! 📱💳*