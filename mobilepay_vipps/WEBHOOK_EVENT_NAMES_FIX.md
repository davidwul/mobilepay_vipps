# 🔧 Webhook Event Names Fix

## ❌ **Issue Identified**:
```
'Unsupported values: epayment.payment.created.v1, epayment.payment.authorized.v1, epayment.payment.captured.v1, epayment.payment.cancelled.v1, epayment.payment.expired.v1, epayment.payment.terminated.v1'
```

## 🔍 **Root Cause**:
The webhook event names were incorrect. We were using:
- ❌ `epayment.payment.created.v1` (missing 's')
- ❌ Multiple events that may not be supported

## ✅ **Fix Applied**:
Updated to use the correct event name from Vipps specification:
- ✅ `epayments.payment.created.v1` (with 's')

## 📋 **What Changed**:

### **Before (Incorrect)**:
```json
{
  "url": "https://odoo17dev.sme-it.dk/payment/vipps/webhook",
  "events": [
    "epayment.payment.created.v1",
    "epayment.payment.authorized.v1", 
    "epayment.payment.captured.v1",
    "epayment.payment.cancelled.v1",
    "epayment.payment.expired.v1",
    "epayment.payment.terminated.v1"
  ]
}
```

### **After (Correct)**:
```json
{
  "url": "https://odoo17dev.sme-it.dk/payment/vipps/webhook",
  "events": [
    "epayments.payment.created.v1"
  ]
}
```

## 🎯 **Why This Approach**:
1. **Start Simple**: Register only the essential payment created event first
2. **Follow Spec**: Use the exact event name from Vipps documentation
3. **Test & Expand**: Add more events later if needed

## 🚀 **Next Steps**:
1. **Try webhook registration again** - should work now
2. **Check for success** in the logs
3. **Verify webhook appears** in webhook status check
4. **Add more events** later if needed for additional functionality

## 📖 **Reference**:
From Vipps documentation:
> "Register to get a webhook when we create a payment. This is the epayments.payment.created.v1 event."

The key difference:
- ❌ `epayment` (singular, no 's')
- ✅ `epayments` (plural, with 's')

## ✅ **Expected Result**:
After this fix, the webhook registration should succeed and you should see:
```
✅ DEBUG: Webhook registration successful
```

Try the "Register Webhook" button again! 🎯