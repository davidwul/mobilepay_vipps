# 🚨 Critical Database & Credential Fixes Applied

## ❌ **Issues Identified**

### 1. **Database Schema Error**
```
ValueError: Invalid field 'vipps_last_credential_update' on model 'payment.provider'
```
**Cause**: Field used in code but not defined in model

### 2. **Client Secret Error**
```
Failed to obtain access token: Value for header {client_secret: False} must be of type str or bytes, not <class 'bool'>
```
**Cause**: Decryption property returning `False` instead of decrypted value

### 3. **Missing Database Columns**
```
ERROR: column payment_provider.vipps_webhook_id does not exist
```
**Cause**: New fields added to model but database schema not updated

## ✅ **Fixes Applied**

### **1. Added Missing Field Definition**
```python
vipps_last_credential_update = fields.Datetime(
    string="Last Credential Update",
    help="Timestamp of the last credential update"
)
```

### **2. Fixed Credential Decryption Properties**
```python
@property
def vipps_client_secret_decrypted(self):
    """Get decrypted client secret"""
    if self.vipps_credentials_encrypted and self.vipps_client_secret_encrypted:
        return self._decrypt_credential(self.vipps_client_secret_encrypted)
    # Return plaintext version only if it's not False
    return self.vipps_client_secret if self.vipps_client_secret else None
```

**Problem**: When credentials were encrypted, plaintext fields were set to `False`, but decryption properties were returning `False` instead of trying to decrypt.

**Solution**: Modified properties to return `None` when plaintext is `False`, forcing use of encrypted version.

### **3. Updated Database Schema Scripts**

#### **Migration Script**: `migrations/1.0.2/post-migration.py`
- Automatically adds missing columns during module upgrade
- Sets default values for new fields
- Handles errors gracefully

#### **Manual Fix Script**: `update_database_schema.py`
- Provides manual database update commands
- Can be run independently if needed
- Includes all missing fields

#### **Quick Fix Guide**: `DATABASE_SCHEMA_FIX.md`
- Step-by-step instructions for fixing database issues
- Multiple fix options (module upgrade, manual SQL, Odoo shell)
- Verification steps

### **4. Updated Module Version**
- Changed from `1.0.1` to `1.0.2`
- Triggers automatic schema update on module upgrade

## 🔧 **Database Columns Added**

| Column Name | Type | Purpose |
|-------------|------|---------|
| `vipps_webhook_id` | varchar | Webhook ID from Vipps API |
| `vipps_system_name` | varchar | System name for HTTP headers |
| `vipps_system_version` | varchar | System version for HTTP headers |
| `vipps_plugin_name` | varchar | Plugin name for HTTP headers |
| `vipps_plugin_version` | varchar | Plugin version for HTTP headers |
| `vipps_last_credential_update` | timestamp | Last credential update time |

## 🚀 **How to Apply Fixes**

### **Option 1: Module Upgrade (Recommended)**
```bash
# Stop Odoo server
python3 odoo-bin -d your_database_name -u payment_vipps_mobilepay
# Restart Odoo server
```

### **Option 2: Manual Database Update**
```sql
-- Connect to PostgreSQL
psql -d your_database_name

-- Add missing columns
ALTER TABLE payment_provider ADD COLUMN IF NOT EXISTS vipps_webhook_id varchar;
ALTER TABLE payment_provider ADD COLUMN IF NOT EXISTS vipps_system_name varchar;
ALTER TABLE payment_provider ADD COLUMN IF NOT EXISTS vipps_system_version varchar;
ALTER TABLE payment_provider ADD COLUMN IF NOT EXISTS vipps_plugin_name varchar;
ALTER TABLE payment_provider ADD COLUMN IF NOT EXISTS vipps_plugin_version varchar;
ALTER TABLE payment_provider ADD COLUMN IF NOT EXISTS vipps_last_credential_update timestamp;

-- Set default values
UPDATE payment_provider 
SET vipps_system_name = 'Odoo ERP',
    vipps_plugin_name = 'vipps-mobilepay-odoo',
    vipps_plugin_version = '1.0.2'
WHERE code = 'vipps';
```

### **Option 3: Use Update Script**
```bash
python3 update_database_schema.py
# Follow the instructions provided
```

## ✅ **Verification Steps**

After applying fixes:

1. **Restart Odoo server**
2. **Check provider configuration** - should load without errors
3. **Test credential validation** - "Validate Credentials" button
4. **Test webhook functionality** - "Register Webhook" and "Check Webhook Status" buttons
5. **Verify no database errors** in server logs

## 🔍 **Root Cause Analysis**

### **Why This Happened**:
1. **Rapid Development**: New fields added without proper migration
2. **Encryption Logic**: Credential encryption clearing plaintext fields
3. **Property Logic**: Decryption properties not handling `False` values correctly
4. **Schema Sync**: Database schema not updated after model changes

### **Prevention Measures**:
1. **Always upgrade modules** after code changes: `-u module_name`
2. **Use migration scripts** for schema changes
3. **Test in development** environment first
4. **Verify credential handling** after encryption changes

## 🎯 **Expected Results**

After applying these fixes:

- ✅ **No more database column errors**
- ✅ **Credential validation works properly**
- ✅ **Access token requests succeed**
- ✅ **Webhook registration functions**
- ✅ **Provider configuration loads without errors**
- ✅ **Payment processing can proceed**

## 🆘 **If Issues Persist**

1. **Check server logs** for additional errors
2. **Verify database permissions**
3. **Ensure all columns were added** using `\d payment_provider` in PostgreSQL
4. **Test credential decryption** manually in Odoo shell
5. **Consider backup restoration** if critical issues occur

These fixes address the core database and credential issues preventing the Vipps/MobilePay integration from functioning properly! 🚀