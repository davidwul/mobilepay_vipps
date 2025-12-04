# 🔧 Unicode Encoding Error Fix

## ❌ **Error Identified**:
```
'latin-1' codec can't encode character '\u2028' in position 32: ordinal not in range(256)
```

## 🔍 **Root Cause**:
The credentials (client_id, client_secret, subscription_key, or merchant_serial_number) contain Unicode characters that can't be encoded in latin-1. This often happens when:

- **Copying from web interfaces** - Invisible Unicode characters get copied
- **Line separators** - `\u2028` is a Unicode line separator character
- **Non-ASCII characters** - Characters outside the ASCII range (0-127)

## ✅ **Fix Applied**:

### **Added Credential Sanitization**:
```python
def sanitize_credential(value):
    if not value:
        return value
    # Remove problematic Unicode characters and ensure ASCII encoding
    return ''.join(char for char in str(value) if ord(char) < 128).strip()
```

### **Applied to Both Methods**:
1. **`_get_access_token()`** - Token request headers
2. **`_get_api_headers()`** - Standard API request headers

### **Sanitized Fields**:
- ✅ `client_id`
- ✅ `client_secret` 
- ✅ `subscription_key`
- ✅ `merchant_serial_number`

## 🎯 **How It Works**:

### **Before (Error)**:
```python
headers = {
    'client_secret': 'abc123\u2028def',  # Contains Unicode line separator
    # ... other headers
}
# → Encoding error when making HTTP request
```

### **After (Working)**:
```python
headers = {
    'client_secret': sanitize_credential('abc123\u2028def'),  # → 'abc123def'
    # ... other headers  
}
# → Clean ASCII-only credentials, no encoding errors
```

## 🔍 **What Gets Removed**:
- **Unicode line separators** (`\u2028`, `\u2029`)
- **Non-ASCII characters** (anything with ord > 127)
- **Leading/trailing whitespace**

## 🚀 **Expected Result**:

After this fix:
1. **No more encoding errors** in API requests
2. **Webhook registration should work** 
3. **Access token requests succeed**
4. **All API calls function normally**

## 💡 **Prevention**:

To avoid this in the future:
- **Type credentials manually** instead of copy-pasting
- **Check for invisible characters** in credential fields
- **Use plain text editors** when handling credentials
- **Validate credentials** before saving

## 🔧 **Testing**:

1. **Try webhook registration** - should work without encoding errors
2. **Test payment flow** - access tokens should be obtained successfully
3. **Check logs** - no more Unicode codec errors

The credentials are now sanitized to ensure they only contain ASCII characters that can be safely encoded for HTTP requests! 🎯