# 🔧 Database Schema Fix Guide

## ❌ **Error**: `column payment_provider.vipps_webhook_id does not exist`

This error occurs when new fields are added to the model but the database schema hasn't been updated yet.

## ✅ **Quick Fix Options**

### **Option 1: Module Upgrade (Recommended)**

1. **Stop Odoo server**
2. **Upgrade the module**:
   ```bash
   python3 odoo-bin -d your_database_name -u payment_vipps_mobilepay
   ```
3. **Restart Odoo server**

### **Option 2: Manual Database Update**

If the module upgrade doesn't work, manually update the database:

1. **Connect to your database** (PostgreSQL):
   ```bash
   psql -d your_database_name
   ```

2. **Add missing columns**:
   ```sql
   -- Add webhook ID field
   ALTER TABLE payment_provider ADD COLUMN IF NOT EXISTS vipps_webhook_id varchar;
   
   -- Add system information fields
   ALTER TABLE payment_provider ADD COLUMN IF NOT EXISTS vipps_system_name varchar;
   ALTER TABLE payment_provider ADD COLUMN IF NOT EXISTS vipps_system_version varchar;
   ALTER TABLE payment_provider ADD COLUMN IF NOT EXISTS vipps_plugin_name varchar;
   ALTER TABLE payment_provider ADD COLUMN IF NOT EXISTS vipps_plugin_version varchar;
   ALTER TABLE payment_provider ADD COLUMN IF NOT EXISTS vipps_last_credential_update timestamp;
   ALTER TABLE payment_provider ADD COLUMN IF NOT EXISTS vipps_webhook_security_logging boolean DEFAULT true;
   
   -- Set default values
   UPDATE payment_provider 
   SET vipps_system_name = 'Odoo ERP',
       vipps_plugin_name = 'vipps-mobilepay-odoo',
       vipps_plugin_version = '1.0.2'
   WHERE code = 'vipps' 
   AND (vipps_system_name IS NULL OR vipps_plugin_name IS NULL OR vipps_plugin_version IS NULL);
   ```

3. **Exit database**:
   ```sql
   \q
   ```

### **Option 3: Odoo Shell Method**

1. **Start Odoo shell**:
   ```bash
   python3 odoo-bin shell -d your_database_name
   ```

2. **Run update commands**:
   ```python
   # Add missing columns
   env.cr.execute("""
       ALTER TABLE payment_provider ADD COLUMN IF NOT EXISTS vipps_webhook_id varchar;
   """)
   env.cr.commit()
   
   env.cr.execute("""
       ALTER TABLE payment_provider ADD COLUMN IF NOT EXISTS vipps_system_name varchar;
   """)
   env.cr.commit()
   
   env.cr.execute("""
       ALTER TABLE payment_provider ADD COLUMN IF NOT EXISTS vipps_system_version varchar;
   """)
   env.cr.commit()
   
   env.cr.execute("""
       ALTER TABLE payment_provider ADD COLUMN IF NOT EXISTS vipps_plugin_name varchar;
   """)
   env.cr.commit()
   
   env.cr.execute("""
       ALTER TABLE payment_provider ADD COLUMN IF NOT EXISTS vipps_plugin_version varchar;
   """)
   env.cr.commit()
   
   # Set default values
   env.cr.execute("""
       UPDATE payment_provider 
       SET vipps_system_name = 'Odoo ERP',
           vipps_plugin_name = 'vipps-mobilepay-odoo',
           vipps_plugin_version = '1.0.2'
       WHERE code = 'vipps' 
       AND (vipps_system_name IS NULL OR vipps_plugin_name IS NULL OR vipps_plugin_version IS NULL);
   """)
   env.cr.commit()
   
   # Exit shell
   exit()
   ```

## ✅ **Verification**

After applying the fix:

1. **Restart Odoo server**
2. **Check if the error is gone** - try accessing the payment provider
3. **Test webhook functionality**:
   - Go to payment provider configuration
   - Click "Check Webhook Status" button
   - Click "Register Webhook" button

## 🔍 **What Happened?**

- New fields were added to the `payment.provider` model
- The database schema wasn't automatically updated
- Odoo tried to query non-existent columns
- This caused the `UndefinedColumn` error

## 🛡️ **Prevention**

To avoid this in the future:
- Always upgrade modules after code changes: `-u module_name`
- Use migration scripts for complex schema changes
- Test in development environment first

## 📋 **Fields Added**

The following new fields were added:
- `vipps_webhook_id` - Webhook ID from Vipps API
- `vipps_system_name` - System name for HTTP headers
- `vipps_system_version` - System version for HTTP headers  
- `vipps_plugin_name` - Plugin name for HTTP headers
- `vipps_plugin_version` - Plugin version for HTTP headers

These fields are required for:
- ✅ Webhook registration and management
- ✅ HTTP headers compliance with Vipps specification
- ✅ Production deployment requirements

## 🆘 **Still Having Issues?**

If the error persists:
1. Check database connection
2. Verify user permissions
3. Check Odoo logs for additional errors
4. Try restarting PostgreSQL service
5. Consider restoring from backup and re-applying changes

The database schema should now be properly updated! 🎯