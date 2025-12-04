#!/usr/bin/env python3
"""
Script to create Vipps payment method
Run this in Odoo shell to create the missing payment method
"""

# Run in Odoo shell:
# exec(open('create_payment_method.py').read())

def create_vipps_payment_method():
    """Create Vipps payment method if it doesn't exist"""
    
    # Check if payment method exists
    PaymentMethod = env['payment.method']
    existing_method = PaymentMethod.search([('code', '=', 'vipps')])
    
    if existing_method:
        print(f"Payment method already exists: {existing_method.name} (active: {existing_method.active})")
        # Make sure it's active
        if not existing_method.active:
            existing_method.active = True
            print("Activated existing payment method")
        return existing_method
    
    # Create new payment method
    payment_method = PaymentMethod.create({
        'name': 'Vipps/MobilePay',
        'code': 'vipps',
        'active': True,
    })
    
    print(f"Created payment method: {payment_method.name} (ID: {payment_method.id})")
    
    # Link to payment provider
    provider = env['payment.provider'].search([('code', '=', 'vipps')], limit=1)
    if provider:
        provider.payment_method_ids = [(4, payment_method.id)]
        print(f"Linked payment method to provider: {provider.name}")
    else:
        print("Warning: No Vipps payment provider found")
    
    return payment_method

# Execute the function
if __name__ == '__main__':
    create_vipps_payment_method()