#!/usr/bin/env python3
"""
Python script to clean up Vipps payment data via Odoo shell
Run with: python3 odoo-bin shell -d your_database_name --shell-interface=ipython
Then execute this script content
"""

print("=== Cleaning up Vipps payment data ===")

# Delete payment transactions first (they reference other tables)
transactions = env['payment.transaction'].search([('provider_code', '=', 'vipps')])
print(f"Found {len(transactions)} Vipps transactions")
if transactions:
    transactions.unlink()
    print("Deleted Vipps transactions")

# Delete payment methods
methods = env['payment.method'].search([('code', '=', 'vipps')])
print(f"Found {len(methods)} Vipps payment methods")
if methods:
    methods.unlink()
    print("Deleted Vipps payment methods")

# Delete payment providers
providers = env['payment.provider'].search([('code', '=', 'vipps')])
print(f"Found {len(providers)} Vipps providers")
if providers:
    providers.unlink()
    print("Deleted Vipps providers")

# Commit the changes
env.cr.commit()
print("=== Cleanup completed ===")
print("You can now try to install the module again")