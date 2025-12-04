# Official Vipps/MobilePay Configuration

## ✅ **Corrected Configuration Based on Official Documentation**

### **Production Environment**
- **API Server**: `https://api.vipps.no`
- **Request Servers (Webhooks)**:
  - `callback-1.vipps.no`
  - `callback-2.vipps.no`
  - `callback-3.vipps.no`
  - `callback-4.vipps.no`
- **Landing Page Server**: `pay.mobilepay.dk`

### **Test Environment**
- **API Server**: `https://api.vipps.no` (same as production!)
- **Request Servers (Webhooks)**:
  - `callback-mt-1.vipps.no`
  - `callback-mt-2.vipps.no`
- **Landing Page Server**: `pay-mt.mobilepay.dk`

## 🔧 **Key Corrections Made**

### 1. **API URLs Unified**
- ❌ **Before**: Test used `https://apitest.vipps.no`
- ✅ **After**: Both environments use `https://api.vipps.no`

### 2. **Test Webhook Hostnames Fixed**
- ❌ **Before**: `callback-mt-*.vippsmobilepay.com`
- ✅ **After**: `callback-mt-*.vipps.no`

### 3. **Hostname Resolution Verified**
```bash
# Production hostnames resolve to multiple IPs
callback-1.vipps.no → 51.105.122.55, 51.105.122.59, etc.
callback-2.vipps.no → 51.105.122.53, 51.105.122.54, etc.

# Test hostnames resolve correctly
callback-mt-1.vipps.no → 51.105.193.243, 51.105.193.245
callback-mt-2.vipps.no → 104.40.253.225, 104.40.255.223, etc.
```

## 📋 **Implementation Details**

### **Files Updated**

1. **`models/vipps_webhook_security.py`**
   - Corrected test hostnames to `callback-mt-*.vipps.no`
   - Environment-specific hostname selection

2. **`controllers/main.py`**
   - Updated webhook IP validation with correct hostnames
   - Real-time DNS resolution

3. **`models/payment_provider.py`**
   - Unified API URLs to use `https://api.vipps.no` for both environments
   - Corrected access token and webhook API URLs

4. **`models/vipps_api_client.py`**
   - Updated API client to use unified API server
   - Removed environment-specific API URL logic

### **Environment Detection Logic**

```python
if provider.vipps_environment == 'production':
    # Use: callback-1.vipps.no, callback-2.vipps.no, etc.
else:
    # Use: callback-mt-1.vipps.no, callback-mt-2.vipps.no
```

## 🎯 **Benefits of Correct Configuration**

### **Reliability**
- ✅ **Correct webhook validation** for both environments
- ✅ **Proper API endpoint usage** as per official docs
- ✅ **No more environment mismatch issues**

### **Security**
- ✅ **Accurate hostname validation** against official servers
- ✅ **Environment-specific security policies**
- ✅ **Real-time DNS resolution** for IP changes

### **Maintainability**
- ✅ **Follows official documentation** exactly
- ✅ **Future-proof** against Vipps infrastructure changes
- ✅ **Clear environment separation**

## 🧪 **Testing Results**

### **Hostname Resolution Test**
```
✅ callback-1.vipps.no        → Multiple IPs resolved
✅ callback-2.vipps.no        → Multiple IPs resolved  
✅ callback-3.vipps.no        → Multiple IPs resolved
✅ callback-4.vipps.no        → Multiple IPs resolved
✅ callback-mt-1.vipps.no     → Multiple IPs resolved
✅ callback-mt-2.vipps.no     → Multiple IPs resolved
```

### **API Endpoint Verification**
- ✅ Both environments use `https://api.vipps.no`
- ✅ Unified access token endpoint
- ✅ Consistent webhook API base URL

## 🚀 **Next Steps**

1. **Test webhook processing** with corrected hostnames
2. **Verify environment switching** works correctly
3. **Re-register webhooks** if needed to ensure proper configuration
4. **Monitor logs** for successful hostname validation

The configuration now matches the official Vipps/MobilePay documentation exactly! 🎉