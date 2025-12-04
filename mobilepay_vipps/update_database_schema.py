#!/usr/bin/env python3
"""
Manual database schema update script for Vipps/MobilePay module
Run this if you're having database column issues after adding new fields
"""

import logging

_logger = logging.getLogger(__name__)

def update_payment_provider_schema():
    """
    Manually update payment_provider table schema
    This should be run in Odoo shell context
    """
    print("🔧 Updating payment_provider table schema...")
    
    # SQL commands to add missing columns
    sql_commands = [
        # Add webhook ID field if missing
        """
        DO $$ 
        BEGIN 
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'payment_provider' 
                AND column_name = 'vipps_webhook_id'
            ) THEN
                ALTER TABLE payment_provider ADD COLUMN vipps_webhook_id varchar;
                RAISE NOTICE 'Added vipps_webhook_id column';
            ELSE
                RAISE NOTICE 'vipps_webhook_id column already exists';
            END IF;
        END $$;
        """,
        
        # Add system information fields if missing
        """
        DO $$ 
        BEGIN 
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'payment_provider' 
                AND column_name = 'vipps_system_name'
            ) THEN
                ALTER TABLE payment_provider ADD COLUMN vipps_system_name varchar;
                RAISE NOTICE 'Added vipps_system_name column';
            ELSE
                RAISE NOTICE 'vipps_system_name column already exists';
            END IF;
        END $$;
        """,
        
        """
        DO $$ 
        BEGIN 
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'payment_provider' 
                AND column_name = 'vipps_system_version'
            ) THEN
                ALTER TABLE payment_provider ADD COLUMN vipps_system_version varchar;
                RAISE NOTICE 'Added vipps_system_version column';
            ELSE
                RAISE NOTICE 'vipps_system_version column already exists';
            END IF;
        END $$;
        """,
        
        """
        DO $$ 
        BEGIN 
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'payment_provider' 
                AND column_name = 'vipps_plugin_name'
            ) THEN
                ALTER TABLE payment_provider ADD COLUMN vipps_plugin_name varchar;
                RAISE NOTICE 'Added vipps_plugin_name column';
            ELSE
                RAISE NOTICE 'vipps_plugin_name column already exists';
            END IF;
        END $$;
        """,
        
        """
        DO $$ 
        BEGIN 
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'payment_provider' 
                AND column_name = 'vipps_plugin_version'
            ) THEN
                ALTER TABLE payment_provider ADD COLUMN vipps_plugin_version varchar;
                RAISE NOTICE 'Added vipps_plugin_version column';
            ELSE
                RAISE NOTICE 'vipps_plugin_version column already exists';
            END IF;
        END $$;
        """,
        
        # Set default values
        """
        UPDATE payment_provider 
        SET vipps_system_name = 'Odoo ERP'
        WHERE code = 'vipps' AND vipps_system_name IS NULL;
        """,
        
        """
        UPDATE payment_provider 
        SET vipps_plugin_name = 'vipps-mobilepay-odoo'
        WHERE code = 'vipps' AND vipps_plugin_name IS NULL;
        """,
        
        """
        UPDATE payment_provider 
        SET vipps_plugin_version = '1.0.2'
        WHERE code = 'vipps' AND vipps_plugin_version IS NULL;
        """,
        
        # Add last credential update field
        """
        DO $$ 
        BEGIN 
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'payment_provider' 
                AND column_name = 'vipps_last_credential_update'
            ) THEN
                ALTER TABLE payment_provider ADD COLUMN vipps_last_credential_update timestamp;
                RAISE NOTICE 'Added vipps_last_credential_update column';
            ELSE
                RAISE NOTICE 'vipps_last_credential_update column already exists';
            END IF;
        END $$;
        """
    ]
    
    return sql_commands

def run_in_odoo_shell():
    """
    Instructions for running in Odoo shell
    """
    print("""
    🔧 To fix the database schema issue, run this in Odoo shell:
    
    # Start Odoo shell
    python3 odoo-bin shell -d your_database_name
    
    # Then run these commands:
    """)
    
    commands = update_payment_provider_schema()
    for i, cmd in enumerate(commands, 1):
        print(f"# Command {i}:")
        print(f"env.cr.execute('''{cmd.strip()}''')")
        print("env.cr.commit()")
        print()
    
    print("""
    # After running all commands, restart Odoo and upgrade the module:
    # python3 odoo-bin -d your_database_name -u payment_vipps_mobilepay
    """)

if __name__ == "__main__":
    print("🔧 Database Schema Update Script")
    print("=" * 50)
    print()
    print("❌ Database column 'vipps_webhook_id' does not exist")
    print("✅ This script will help you fix the database schema")
    print()
    
    run_in_odoo_shell()