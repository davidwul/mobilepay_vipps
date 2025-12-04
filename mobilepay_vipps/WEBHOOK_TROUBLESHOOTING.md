# 🔧 Webhook Registration Troubleshooting Guide

## Issue: Webhook Not Being Created

The webhook registration is implemented but may be failing silently. Here's how to debug and fix it:

## ✅ **Step 1: Check Current Status**

### In Odoo UI:
1. Go to your Vipps payment provider configuration
2. Click **"Check Webhook Status"** button
3. This will show you if the webhook is registered with Vipps

### Expected Results:
- ✅ **Success**: "Webhook is registered!" with webhook ID and URL
- ❌ **Not Found**: "Webhook not found!" with list of registered webhooks
- ❌ **Error**: API connection issues

## ✅ **Step 2: Manual Registration**

### In Odoo UI:
1. Ensure your provider is **enabled** (state = 'enabled')
2. Ensure credentials are **validated** (green checkmark)
3. Click **"Register Webhook"** button
4. Check the notification message

### Expected Results:
- ✅ **Success**: "Webhook registered successfully with Vipps!"
- ❌ **Failed**: "Failed to register webhook. Check logs for details."

## ✅ **Step 3: Check Server Logs**

### Enable Debug Logging:
Look for these log messages in your Odoo server logs:

```
🔧 DEBUG: Registering Webhook with Vipps
🔧 Environment: test
🔧 Provider: Vipps/MobilePay (ID: 1)
🔧 DEBUG: Webhook URL: https://your-domain.com/payment/vipps/webhook
🔧 DEBUG: Webhook Registration Payload: {...}
🔧 DEBUG: Vipps Webhook API Request Details
🔧 Method: POST
🔧 URL: https://apitest.vipps.no/webhooks/v1/webhooks
✅ DEBUG: Webhook registration successful
```

### Common Error Messages:
- `❌ DEBUG: Webhook registration failed with status 401` → **Credentials issue**
- `❌ DEBUG: Webhook registration failed with status 400` → **Invalid payload**
- `❌ DEBUG: Webhook registration exception: ...` → **Network/API issue**

## ✅ **Step 4: Common Issues & Solutions**

### 🔴 **Issue: 401 Unauthorized**
**Cause**: Invalid or expired credentials
**Solution**: 
1. Re-validate credentials using "Validate Credentials" button
2. Check that all required fields are filled
3. Verify credentials in Vipps Developer Portal

### 🔴 **Issue: 400 Bad Request**
**Cause**: Invalid webhook payload or URL
**Solution**:
1. Check that your Odoo instance is accessible from the internet
2. Verify webhook URL format: `https://your-domain.com/payment/vipps/webhook`
3. Ensure HTTPS is enabled (required by Vipps)

### 🔴 **Issue: Network Timeout**
**Cause**: Connectivity issues
**Solution**:
1. Check internet connection
2. Verify firewall settings
3. Test API connectivity manually

### 🔴 **Issue: Webhook URL Not Accessible**
**Cause**: Vipps cannot reach your webhook endpoint
**Solution**:
1. Ensure your Odoo instance is publicly accessible
2. Test webhook URL manually: `curl https://your-domain.com/payment/vipps/webhook`
3. Check SSL certificate validity
4. Verify no authentication required for webhook endpoint

## ✅ **Step 5: Manual Testing**

### Test Webhook Endpoint:
```bash
# Test if your webhook endpoint is accessible
curl -X POST https://your-domain.com/payment/vipps/webhook \
  -H "Content-Type: application/json" \
  -d '{"test": "webhook"}'
```

### Expected Response:
- Should return HTTP 200 or appropriate response
- Should not require authentication
- Should be accessible from external networks

## ✅ **Step 6: Automatic Registration Triggers**

Webhook registration is automatically triggered when:

1. **Provider is enabled**: `state` changed to 'enabled'
2. **Credentials updated**: Any credential field is modified
3. **Manual trigger**: "Register Webhook" button clicked

### Check Auto-Registration:
1. Disable the provider
2. Enable the provider
3. Check logs for webhook registration messages

## ✅ **Step 7: Webhook Configuration Details**

### Webhook URL Format:
```
https://your-domain.com/payment/vipps/webhook
```

### Registered Events:
- `epayment.payment.created.v1`
- `epayment.payment.authorized.v1`
- `epayment.payment.captured.v1`
- `epayment.payment.cancelled.v1`
- `epayment.payment.expired.v1`
- `epayment.payment.terminated.v1`

### API Endpoint Used:
- **Test**: `https://apitest.vipps.no/webhooks/v1/webhooks`
- **Production**: `https://api.vipps.no/webhooks/v1/webhooks`

## ✅ **Step 8: Debug Information**

### Provider Configuration Check:
```python
# In Odoo shell or debug mode
provider = self.env['payment.provider'].search([('code', '=', 'vipps')])
print(f"Provider State: {provider.state}")
print(f"Credentials Validated: {provider.vipps_credentials_validated}")
print(f"Webhook URL: {provider.vipps_webhook_url}")
print(f"Webhook ID: {provider.vipps_webhook_id}")
print(f"Environment: {provider.vipps_environment}")
```

### Manual Registration Test:
```python
# In Odoo shell
provider = self.env['payment.provider'].search([('code', '=', 'vipps')])
result = provider._register_webhook()
print(f"Registration Result: {result}")
```

## ✅ **Step 9: Verification**

After successful registration, verify:

1. **Webhook ID**: Should be populated in provider configuration
2. **Webhook Status**: "Check Webhook Status" should show success
3. **Test Payment**: Create a test payment and verify webhook is called
4. **Logs**: Should show webhook events being received

## 🆘 **Still Having Issues?**

If webhook registration still fails:

1. **Check Vipps Developer Portal**: Verify your app configuration
2. **Test Environment**: Ensure you're using correct test credentials
3. **Network**: Verify your server can reach Vipps APIs
4. **SSL**: Ensure valid SSL certificate on your domain
5. **Firewall**: Check that outbound HTTPS is allowed

## 📋 **Quick Checklist**

- [ ] Provider is enabled
- [ ] Credentials are validated
- [ ] Webhook URL is publicly accessible
- [ ] HTTPS is enabled and valid
- [ ] No authentication required for webhook endpoint
- [ ] Outbound HTTPS connections allowed
- [ ] Correct API environment (test/production)
- [ ] All required fields filled in provider configuration

## 🔍 **Debug Commands**

### Check webhook registration status:
```bash
# Check if webhook endpoint responds
curl -I https://your-domain.com/payment/vipps/webhook

# Test webhook with sample data
curl -X POST https://your-domain.com/payment/vipps/webhook \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test" \
  -d '{"eventType": "epayment.payment.created.v1", "data": {}}'
```

This should help you identify and resolve the webhook registration issue! 🎯