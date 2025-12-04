# Corrected Official Vipps/MobilePay Configuration

## ✅ **Final Correct Configuration**

### **Production Environment**
- **API Server**: `https://api.vipps.no`
- **Request Servers (Webhooks)**:
  - `callback-1.vipps.no`
  - `callback-2.vipps.no`
  - `callback-3.vipps.no`
  - `callback-4.vipps.no`
- **Landing Page Server**: `pay.mobilepay.dk`

### **Test Environment**
- **API Server**: `https://apitest.vipps.no` ⚠️ **DIFFERENT FROM PRODUCTION**
- **Request Servers (Webhooks)**:
  - `callback-mt-1.vipps.no`
  - `callback-mt-2.vipps.no`
- **Landing Page Server**: `pay-mt.mobilepay.dk`

## 🔧 **Final Corrections Applied**

### 1. **API URLs - Environment Specific**
- ✅ **Production**: `https://api.vipps.no`
- ✅ **Test**: `https://apitest.vipps.no`

### 2. **Webhook Callback Hostnames**
- ✅ **Production**: `callback-1.vipps.no` through `callback-4.vipps.no`
- ✅ **Test**: `callback-mt-1.vipps.no` and `callback-mt-2.vipps.no`

### 3. **Environment Detection Logic**
```python
# API URLs
if provider.vipps_environment == 'production':
    api_url = "https://api.vipps.no"
else:
    api_url = "https://apitest.vipps.no"

# Webhook hostnames  
if provider.vipps_environment == 'production':
    hostnames = ['callback-1.vipps.no', 'callback-2.vipps.no', ...]
else:
    hostnames = ['callback-mt-1.vipps.no', 'callback-mt-2.vipps.no']
```

## 📋 **Implementation Summary**

### **Files Updated with Correct Configuration**

1. **`models/payment_provider.py`**
   ```python
   def _get_vipps_api_url(self):
       if self.vipps_environment == 'production':
           return "https://api.vipps.no/epayment/v1/"
       else:
           return "https://apitest.vipps.no/epayment/v1/"
   ```

2. **`models/vipps_api_client.py`**
   ```python
   def _get_api_base_url(self):
       if self.provider.vipps_environment == 'production':
           return "https://api.vipps.no/epayment/v1"
       else:
           return "https://apitest.vipps.no/epayment/v1"
   ```

3. **`models/vipps_webhook_security.py`**
   ```python
   def _get_allowed_hostnames(self, provider):
       if provider.vipps_environment == 'production':
           return ['callback-1.vipps.no', 'callback-2.vipps.no', ...]
       else:
           return ['callback-mt-1.vipps.no', 'callback-mt-2.vipps.no']
   ```

## 🎯 **Key Differences Between Environments**

| Component | Production | Test |
|-----------|------------|------|
| **API Server** | `api.vipps.no` | `apitest.vipps.no` |
| **Webhook Servers** | `callback-*.vipps.no` | `callback-mt-*.vipps.no` |
| **Landing Page** | `pay.mobilepay.dk` | `pay-mt.mobilepay.dk` |
| **Credentials** | Production MSN/Keys | Test MSN/Keys |
| **Webhook Secret** | Production Secret | Test Secret |

## 🚀 **Expected Behavior**

With the corrected configuration:

### **Test Environment**
- ✅ API calls go to `https://apitest.vipps.no`
- ✅ Webhooks validated against `callback-mt-*.vipps.no`
- ✅ Uses test credentials and webhook secret

### **Production Environment**  
- ✅ API calls go to `https://api.vipps.no`
- ✅ Webhooks validated against `callback-*.vipps.no`
- ✅ Uses production credentials and webhook secret

## 🔍 **Verification**

The system now correctly:
1. **Routes API calls** to environment-specific servers
2. **Validates webhooks** against correct callback hostnames
3. **Uses appropriate credentials** for each environment
4. **Maintains proper separation** between test and production

This should resolve the environment mismatch issues and ensure webhooks are validated correctly! 🎉