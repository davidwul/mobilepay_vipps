# Vipps/MobilePay Environment Mismatch Solution

## Problem Identified ✅

You are absolutely correct! The issue is likely an **environment mismatch** between:
- The selected environment in Odoo (test/production)
- The actual credentials and webhook secrets being used

## Root Cause

When switching between test and production environments, several things need to be synchronized:

1. **API Credentials**: Different for test vs production
2. **Merchant Serial Number**: Different for test vs production  
3. **Webhook Secret**: Generated separately for each environment
4. **API URLs**: Automatically handled (✅ already working)

## Common Scenarios

### Scenario 1: Using Production Credentials with Test Environment
- Provider set to "test" in Odoo
- But using production MSN, client ID, client secret
- Webhook secret from production environment
- **Result**: Signature validation fails

### Scenario 2: Using Test Credentials with Production Environment  
- Provider set to "production" in Odoo
- But using test MSN, client ID, client secret
- Webhook secret from test environment
- **Result**: Signature validation fails

### Scenario 3: Stale Webhook Secret
- Environment changed but webhook not re-registered
- Old webhook secret still in database
- **Result**: Signature validation fails

## Solution Steps

### Step 1: Verify Current Configuration
1. Check provider environment setting: `vipps_environment`
2. Verify credentials match the selected environment
3. Check webhook secret is for correct environment

### Step 2: Use New Re-registration Feature
I've added a new button: **"Re-register Webhook (New Secret)"**

This will:
1. Unregister current webhook from Vipps
2. Clear old webhook ID and secret
3. Register new webhook with fresh secret
4. Ensure everything matches current environment

### Step 3: Manual Environment Switch Process
When switching environments:

1. **Change Environment Setting** in Odoo
2. **Update Credentials** to match new environment:
   - Merchant Serial Number
   - Client ID  
   - Client Secret
   - Subscription Key
3. **Click "Re-register Webhook (New Secret)"**
4. **Test Payment** to verify everything works

## Quick Fix for Current Issue

Since you suspect environment mismatch:

1. **Go to Payment Provider configuration**
2. **Verify environment setting** matches your intended environment
3. **Check credentials** are for the correct environment
4. **Click "Re-register Webhook (New Secret)"** button
5. **Test webhook** with a new payment

## Code Changes Made

### 1. Added Webhook Re-registration Method
```python
def action_force_webhook_reregistration(self):
    """Force webhook re-registration with new secret"""
    # Unregister old webhook
    # Clear webhook data  
    # Register fresh webhook
```

### 2. Added UI Button
- New button in provider configuration
- Warns user about creating new secret
- Available to system administrators

### 3. Enhanced Environment Handling
- Better logging for environment detection
- Clearer error messages for mismatches

## Testing the Fix

After re-registering webhook:

1. **Check logs** for successful registration
2. **Trigger test payment** 
3. **Verify webhook** receives and processes correctly
4. **Confirm signature validation** passes

## Expected Results

✅ **Webhook signature validation passes**  
✅ **Payments process successfully**  
✅ **No more 401 Unauthorized errors**  
✅ **Proper environment-specific behavior**

## Prevention

To avoid future environment mismatches:

1. **Document credentials** for each environment
2. **Use environment-specific naming** for providers
3. **Always re-register webhooks** after environment changes
4. **Test thoroughly** after any configuration changes

The environment mismatch is a very common issue with Vipps/MobilePay integration - you identified the root cause perfectly! 🎯