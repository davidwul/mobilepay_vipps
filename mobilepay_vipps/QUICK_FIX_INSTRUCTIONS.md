# 🚨 IMMEDIATE FIX REQUIRED

## ❌ **Current Error**:
```
ValueError: Invalid field 'vipps_last_credential_update' on model 'payment.provider'
```

## ⚡ **QUICK FIX - Apply Immediately**

### **Option 1: Direct SQL (Fastest)**

1. **Connect to your PostgreSQL database**:
   ```bash
   psql -d your_database_name
   ```

2. **Run this single command**:
   ```sql
   ALTER TABLE payment_provider ADD COLUMN IF NOT EXISTS vipps_last_credential_update timestamp;
   ```

3. **Exit database**:
   ```sql
   \q
   ```

4. **Refresh your Odoo page** - the error should be gone!

### **Option 2: Run the Complete Fix**

1. **Connect to PostgreSQL**:
   ```bash
   psql -d your_database_name
   ```

2. **Run the complete fix file**:
   ```bash
   \i IMMEDIATE_FIX.sql
   ```

3. **Exit and refresh Odoo**

### **Option 3: Odoo Shell Method**

1. **Open terminal and run**:
   ```bash
   python3 odoo-bin shell -d your_database_name
   ```

2. **Execute this command**:
   ```python
   env.cr.execute("ALTER TABLE payment_provider ADD COLUMN IF NOT EXISTS vipps_last_credential_update timestamp;")
   env.cr.commit()
   exit()
   ```

3. **Restart Odoo server**

## 🎯 **What This Does**

- Adds the missing `vipps_last_credential_update` column to the database
- Fixes the immediate error you're seeing
- Allows you to continue working with the provider configuration

## ✅ **After the Fix**

1. **Refresh your Odoo page**
2. **The error should be gone**
3. **You can continue configuring your Vipps provider**
4. **Test the "Validate Credentials" button**

## 🔄 **Then Apply Complete Fix**

After the immediate fix works, you should still:

1. **Upgrade the module** to get all fixes:
   ```bash
   python3 odoo-bin -d your_database_name -u payment_vipps_mobilepay
   ```

2. **Or run the complete SQL fix** from `IMMEDIATE_FIX.sql`

This will ensure all webhook fields are properly added and configured.

## 🆘 **If You Can't Access Database Directly**

If you can't run SQL commands directly, you'll need to:

1. **Stop Odoo server**
2. **Upgrade the module**:
   ```bash
   python3 odoo-bin -d your_database_name -u payment_vipps_mobilepay
   ```
3. **Start Odoo server**

The migration script should automatically add the missing fields.

**The quickest fix is Option 1 - just add the missing column directly!** ⚡