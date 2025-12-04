# Hostname-Based Webhook Validation Implementation

## Overview ✅

Implemented hostname-based webhook validation instead of hardcoded IP addresses, following Vipps/MobilePay best practices from their official documentation.

## Changes Made

### 1. Environment-Specific Hostnames

**Production Environment:**
```
callback-1.vipps.no
callback-2.vipps.no  
callback-3.vipps.no
callback-4.vipps.no
```

**Test Environment:**
```
callback-1.vippsmobilepay.com
callback-2.vippsmobilepay.com
callback-3.vippsmobilepay.com
callback-4.vippsmobilepay.com
```

### 2. Dynamic DNS Resolution

- **Real-time hostname resolution** instead of static IP lists
- **Automatic IP updates** when Vipps changes server IPs
- **IPv4 and IPv6 support** for future compatibility

### 3. Environment-Aware Validation

The system now:
- ✅ **Automatically selects correct hostnames** based on provider environment setting
- ✅ **Resolves hostnames to current IP addresses** at runtime
- ✅ **Validates webhook source** against resolved IPs
- ✅ **Allows development IPs** in test environment

## Code Implementation

### Security Manager (`models/vipps_webhook_security.py`)

```python
def _get_allowed_hostnames(self, provider):
    """Get environment-specific hostnames"""
    if provider.vipps_environment == 'production':
        return ['callback-1.vipps.no', 'callback-2.vipps.no', ...]
    else:
        return ['callback-1.vippsmobilepay.com', ...]

def _resolve_hostname_to_ips(self, hostname):
    """Resolve hostname to IP addresses"""
    # Uses socket.getaddrinfo() for robust DNS resolution
    
def _validate_source_ip(self, client_ip, provider):
    """Validate against resolved hostnames"""
    # Resolves hostnames and validates client IP
```

### Controller (`controllers/main.py`)

```python
def _validate_webhook_ip(self, request_ip, provider):
    """Environment-aware hostname validation"""
    # Selects correct hostnames based on environment
    # Resolves and validates in real-time
```

## Benefits

### 🔒 **Security**
- **No hardcoded IPs** that become outdated
- **Environment isolation** - test/prod use different hostnames
- **Real-time validation** against current Vipps infrastructure

### 🚀 **Reliability** 
- **Automatic adaptation** to Vipps IP changes
- **No maintenance required** when Vipps updates servers
- **Reduced false rejections** from IP changes

### 🛠️ **Maintainability**
- **Follows official documentation** recommendations
- **Environment-specific configuration** 
- **Clear separation** between test and production

## Environment Behavior

### Production Environment
- Uses `*.vipps.no` hostnames
- Strict validation against production servers
- No development IP allowances

### Test Environment  
- Uses `*.vippsmobilepay.com` hostnames
- Allows localhost and private networks
- More permissive for development

## Configuration Options

### System Parameters
- `vipps.webhook.allowed_hostnames` - Override default hostnames
- Comma-separated list of custom hostnames if needed

### Provider-Specific
- `vipps_webhook_allowed_hostnames` field (if added to provider model)
- Per-provider hostname overrides

## Fallback Behavior

If hostname resolution fails:
- **Logs warning** with resolution error
- **Continues validation** with other hostnames
- **Fails open** for development environments
- **Maintains security** for production

## Testing

The system now properly handles:
- ✅ **Environment switching** - correct hostnames selected
- ✅ **DNS resolution** - real-time IP lookup
- ✅ **IP validation** - matches resolved addresses
- ✅ **Development support** - localhost/private networks allowed in test

## Migration from IP-Based

- **Automatic migration** - no configuration changes needed
- **Backward compatibility** - system parameters still supported
- **Improved accuracy** - no more outdated IP rejections

This implementation aligns with Vipps/MobilePay recommendations and provides a more robust, maintainable solution for webhook validation! 🎯