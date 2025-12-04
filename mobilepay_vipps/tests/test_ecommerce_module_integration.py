
import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, Mock

from odoo.tests.common import TransactionCase, HttpCase
from odoo.exceptions import ValidationError, UserError


class TestVippsEcommerceModuleIntegration(TransactionCase):
    """Integration tests for Vipps/MobilePay with eCommerce module"""
    
    def setUp(self):
        super().setUp()
        
        # Create test company
        self.company = self.env['res.company'].create({
            'name': 'eCommerce Integration Test Company',
            'currency_id': self.env.ref('base.NOK').id,
        })
        
        # Create payment provider
        self.provider = self.env['payment.provider'].create({
            'name': 'Vipps eCommerce Integration',
            'code': 'vipps',
            'state': 'test',
            'company_id': self.company.id,
            'vipps_merchant_serial_number': '123456',
            'vipps_subscription_key': 'test_subscription_key_12345678901234567890',
            'vipps_client_id': 'test_client_id_12345',
            'vipps_client_secret': 'test_client_secret_12345678901234567890',
            'vipps_environment': 'test',
            'vipps_webhook_secret': 'test_webhook_secret_12345678901234567890123456789012',
        })
        
        # Create website
        self.website = self.env['website'].create({
            'name': 'Test eCommerce Site',
            'domain': 'test-ecommerce.com',
            'company_id': self.company.id,
        })
        
        # Create test customer
        self.customer = self.env['res.partner'].create({
            'name': 'eCommerce Test Customer',
            'email': 'ecommerce.test@example.com',
            'phone': '+4712345678',
            'is_company': False,
        })
        
        # Create test products
        self.product_a = self.env['product.product'].create({
            'name': 'eCommerce Product A',
            'type': 'product',
            'list_price': 150.0,
            'website_published': True,
            'is_published': True,
        })
        
        self.product_b = self.env['product.product'].create({
            'name': 'eCommerce Product B',
            'type': 'product',
            'list_price': 250.0,
            'website_published': True,
            'is_published': True,
        })
        
        # Create product categories
        self.category = self.env['product.public.category'].create({
            'name': 'Test Category',
            'website_id': self.website.id,
        })
        
        # Set up website sale configuration
        self.website.payment_provider_ids = [(6, 0, [self.provider.id])]
    
    def test_website_checkout_with_vipps(self):
        """Test complete website checkout flow with Vipps payment"""
        # Create sale order (simulating website checkout)
        sale_order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'website_id': self.website.id,
            'company_id': self.company.id,
            'order_line': [
                (0, 0, {
                    'product_id': self.product_a.id,
                    'product_uom_qty': 2,
                    'price_unit': 150.0,
                }),
                (0, 0, {
                    'product_id': self.product_b.id,
                    'product_uom_qty': 1,
                    'price_unit': 250.0,
                }),
            ],
        })
        
        # Verify order creation
        self.assertEqual(sale_order.amount_total, 550.0)
        self.assertEqual(sale_order.website_id, self.website)
        
        # Create payment transaction for checkout
        payment_transaction = self.env['payment.transaction'].create({
            'reference': sale_order.name,
            'amount': sale_order.amount_total,
            'currency_id': sale_order.currency_id.id,
            'partner_id': sale_order.partner_id.id,
            'provider_id': self.provider.id,
            'sale_order_ids': [(6, 0, [sale_order.id])],
            'state': 'draft',
        })
        
        # Mock Vipps payment processing
        with patch.object(self.provider, '_vipps_make_request') as mock_request:
            mock_request.return_value = {
                'orderId': sale_order.name,
                'url': 'https://api.vipps.no/dwo-api-application/v1/deeplink/vippsgateway?v=2&token=test123',
                'state': 'CREATED'
            }
            
            # Process payment
            payment_transaction._send_payment_request()
            
            # Simulate successful payment
            payment_transaction._set_done()
            
            # Verify checkout completion
            self.assertEqual(payment_transaction.state, 'done')
            self.assertEqual(sale_order.state, 'sale')
    
    def test_shopping_cart_integration(self):
        """Test shopping cart integration with Vipps payment"""
        # Create website visitor session
        website_visitor = self.env['website.visitor'].create({
            'access_token': 'test_visitor_token',
            'website_id': self.website.id,
        })
        
        # Create sale order (cart)
        cart_order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'website_id': self.website.id,
            'state': 'draft',
            'website_order_line': [
                (0, 0, {
                    'product_id': self.product_a.id,
                    'product_uom_qty': 1,
                    'price_unit': 150.0,
                }),
            ],
        })
        
        # Add more items to cart
        cart_line = self.env['sale.order.line'].create({
            'order_id': cart_order.id,
            'product_id': self.product_b.id,
            'product_uom_qty': 2,
            'price_unit': 250.0,
        })
        
        # Verify cart totals
        self.assertEqual(cart_order.amount_total, 650.0)  # 150 + (250 * 2)
        self.assertEqual(len(cart_order.order_line), 2)
        
        # Proceed to checkout with Vipps
        payment_transaction = self.env['payment.transaction'].create({
            'reference': cart_order.name,
            'amount': cart_order.amount_total,
            'currency_id': cart_order.currency_id.id,
            'partner_id': cart_order.partner_id.id,
            'provider_id': self.provider.id,
            'sale_order_ids': [(6, 0, [cart_order.id])],
            'state': 'pending',
        })
        
        # Mock successful payment
        with patch.object(self.provider, '_vipps_make_request') as mock_request:
            mock_request.return_value = {
                'orderId': cart_order.name,
                'state': 'CAPTURED'
            }
            
            payment_transaction._set_done()
            
            # Verify cart conversion to order
            self.assertEqual(payment_transaction.state, 'done')
            cart_order.action_confirm()
            self.assertEqual(cart_order.state, 'sale')
    
    def test_product_variant_checkout(self):
        """Test checkout with product variants and Vipps payment"""
        # Create product template with variants
        product_template = self.env['product.template'].create({
            'name': 'Variant Product',
            'list_price': 100.0,
            'website_published': True,
        })
        
        # Create product attributes
        color_attribute = self.env['product.attribute'].create({
            'name': 'Color',
            'display_type': 'radio',
        })
        
        size_attribute = self.env['product.attribute'].create({
            'name': 'Size',
            'display_type': 'select',
        })
        
        # Create attribute values
        red_value = self.env['product.attribute.value'].create({
            'name': 'Red',
            'attribute_id': color_attribute.id,
        })
        
        large_value = self.env['product.attribute.value'].create({
            'name': 'Large',
            'attribute_id': size_attribute.id,
        })
        
        # Create product variant
        variant = self.env['product.product'].create({
            'product_tmpl_id': product_template.id,
            'product_template_attribute_value_ids': [
                (0, 0, {
                    'attribute_id': color_attribute.id,
                    'product_attribute_value_id': red_value.id,
                }),
                (0, 0, {
                    'attribute_id': size_attribute.id,
                    'product_attribute_value_id': large_value.id,
                }),
            ],
        })
        
        # Create order with variant
        variant_order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'website_id': self.website.id,
            'order_line': [
                (0, 0, {
                    'product_id': variant.id,
                    'product_uom_qty': 1,
                    'price_unit': 100.0,
                }),
            ],
        })
        
        # Process payment for variant
        payment_transaction = self.env['payment.transaction'].create({
            'reference': variant_order.name,
            'amount': variant_order.amount_total,
            'currency_id': variant_order.currency_id.id,
            'partner_id': variant_order.partner_id.id,
            'provider_id': self.provider.id,
            'sale_order_ids': [(6, 0, [variant_order.id])],
            'state': 'done',
        })
        
        # Verify variant order processing
        self.assertEqual(variant_order.order_line[0].product_id, variant)
        self.assertEqual(payment_transaction.amount, 100.0)
    
    def test_coupon_discount_with_vipps(self):
        """Test coupon/discount integration with Vipps payment"""
        # Create coupon program
        coupon_program = self.env['coupon.program'].create({
            'name': 'Test Discount Program',
            'program_type': 'coupon_program',
            'discount_type': 'percentage',
            'discount_percentage': 20.0,
            'minimum_amount': 100.0,
        })
        
        # Generate coupon
        coupon = self.env['coupon.coupon'].create({
            'program_id': coupon_program.id,
            'code': 'TEST20OFF',
        })
        
        # Create order
        discount_order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'website_id': self.website.id,
            'order_line': [
                (0, 0, {
                    'product_id': self.product_a.id,
                    'product_uom_qty': 2,
                    'price_unit': 150.0,
                }),
            ],
        })
        
        # Apply coupon
        discount_order.apply_coupon_code('TEST20OFF')
        
        # Verify discount application
        discount_lines = discount_order.order_line.filtered(lambda l: l.is_reward_line)
        if discount_lines:
            discount_amount = abs(sum(discount_lines.mapped('price_total')))
            expected_discount = 300.0 * 0.20  # 20% of 300
            self.assertEqual(discount_amount, expected_discount)
        
        # Process payment with discount
        final_amount = discount_order.amount_total
        payment_transaction = self.env['payment.transaction'].create({
            'reference': discount_order.name,
            'amount': final_amount,
            'currency_id': discount_order.currency_id.id,
            'partner_id': discount_order.partner_id.id,
            'provider_id': self.provider.id,
            'sale_order_ids': [(6, 0, [discount_order.id])],
            'state': 'done',
        })
        
        # Verify discounted payment
        self.assertLess(payment_transaction.amount, 300.0)  # Should be less than original
    
    def test_shipping_integration_with_payment(self):
        """Test shipping method integration with Vipps payment"""
        # Create delivery carrier
        delivery_carrier = self.env['delivery.carrier'].create({
            'name': 'Test Shipping',
            'delivery_type': 'fixed',
            'fixed_price': 50.0,
            'website_published': True,
        })
        
        # Create order with shipping
        shipping_order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'website_id': self.website.id,
            'carrier_id': delivery_carrier.id,
            'order_line': [
                (0, 0, {
                    'product_id': self.product_a.id,
                    'product_uom_qty': 1,
                    'price_unit': 150.0,
                }),
            ],
        })
        
        # Add delivery line
        shipping_order.set_delivery_line()
        
        # Verify shipping cost inclusion
        delivery_lines = shipping_order.order_line.filtered(lambda l: l.is_delivery)
        if delivery_lines:
            self.assertEqual(delivery_lines[0].price_unit, 50.0)
            self.assertEqual(shipping_order.amount_total, 200.0)  # 150 + 50
        
        # Process payment including shipping
        payment_transaction = self.env['payment.transaction'].create({
            'reference': shipping_order.name,
            'amount': shipping_order.amount_total,
            'currency_id': shipping_order.currency_id.id,
            'partner_id': shipping_order.partner_id.id,
            'provider_id': self.provider.id,
            'sale_order_ids': [(6, 0, [shipping_order.id])],
            'state': 'done',
        })
        
        # Verify payment includes shipping
        self.assertEqual(payment_transaction.amount, shipping_order.amount_total)
    
    def test_guest_checkout_with_vipps(self):
        """Test guest checkout (no account) with Vipps payment"""
        # Create guest customer
        guest_customer = self.env['res.partner'].create({
            'name': 'Guest Customer',
            'email': 'guest@example.com',
            'phone': '+4798765432',
            'is_company': False,
        })
        
        # Create guest order
        guest_order = self.env['sale.order'].create({
            'partner_id': guest_customer.id,
            'website_id': self.website.id,
            'order_line': [
                (0, 0, {
                    'product_id': self.product_a.id,
                    'product_uom_qty': 1,
                    'price_unit': 150.0,
                }),
            ],
        })
        
        # Process guest payment
        payment_transaction = self.env['payment.transaction'].create({
            'reference': guest_order.name,
            'amount': guest_order.amount_total,
            'currency_id': guest_order.currency_id.id,
            'partner_id': guest_order.partner_id.id,
            'provider_id': self.provider.id,
            'sale_order_ids': [(6, 0, [guest_order.id])],
            'state': 'pending',
        })
        
        # Mock Vipps payment with profile data
        with patch.object(self.provider, '_vipps_make_request') as mock_request:
            mock_request.return_value = {
                'orderId': guest_order.name,
                'state': 'CAPTURED',
                'userInfo': {
                    'name': 'Guest Customer',
                    'email': 'guest@example.com',
                    'phoneNumber': '+4798765432'
                }
            }
            
            payment_transaction._set_done()
            
            # Verify guest checkout completion
            self.assertEqual(payment_transaction.state, 'done')
            self.assertEqual(guest_order.partner_id.email, 'guest@example.com')
    
    def test_abandoned_cart_recovery(self):
        """Test abandoned cart recovery with Vipps payment links"""
        # Create abandoned cart
        abandoned_cart = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'website_id': self.website.id,
            'state': 'draft',
            'order_line': [
                (0, 0, {
                    'product_id': self.product_a.id,
                    'product_uom_qty': 1,
                    'price_unit': 150.0,
                }),
            ],
        })
        
        # Simulate cart abandonment (no payment for some time)
        abandoned_cart.write({
            'date_order': datetime.now() - timedelta(hours=2)
        })
        
        # Create recovery payment link
        recovery_transaction = self.env['payment.transaction'].create({
            'reference': f'RECOVERY-{abandoned_cart.name}',
            'amount': abandoned_cart.amount_total,
            'currency_id': abandoned_cart.currency_id.id,
            'partner_id': abandoned_cart.partner_id.id,
            'provider_id': self.provider.id,
            'sale_order_ids': [(6, 0, [abandoned_cart.id])],
            'state': 'draft',
        })
        
        # Mock recovery payment processing
        with patch.object(self.provider, '_vipps_make_request') as mock_request:
            mock_request.return_value = {
                'orderId': recovery_transaction.reference,
                'url': 'https://api.vipps.no/recovery-link',
                'state': 'CREATED'
            }
            
            # Send recovery link
            recovery_transaction._send_payment_request()
            
            # Customer completes payment
            recovery_transaction._set_done()
            
            # Verify cart recovery
            self.assertEqual(recovery_transaction.state, 'done')
            abandoned_cart.action_confirm()
            self.assertEqual(abandoned_cart.state, 'sale')
    
    def test_subscription_ecommerce_integration(self):
        """Test subscription product integration with Vipps payment"""
        # Create subscription product
        subscription_product = self.env['product.product'].create({
            'name': 'Monthly Subscription',
            'type': 'service',
            'list_price': 99.0,
            'website_published': True,
            'recurring_invoice': True,
        })
        
        # Create subscription order
        subscription_order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'website_id': self.website.id,
            'order_line': [
                (0, 0, {
                    'product_id': subscription_product.id,
                    'product_uom_qty': 1,
                    'price_unit': 99.0,
                }),
            ],
        })
        
        # Process initial subscription payment
        payment_transaction = self.env['payment.transaction'].create({
            'reference': subscription_order.name,
            'amount': subscription_order.amount_total,
            'currency_id': subscription_order.currency_id.id,
            'partner_id': subscription_order.partner_id.id,
            'provider_id': self.provider.id,
            'sale_order_ids': [(6, 0, [subscription_order.id])],
            'state': 'done',
        })
        
        # Verify subscription setup
        self.assertEqual(payment_transaction.amount, 99.0)
        self.assertTrue(subscription_product.recurring_invoice)
    
    def test_website_multi_language_checkout(self):
        """Test multi-language website checkout with Vipps"""
        # Create Norwegian language
        norwegian_lang = self.env['res.lang'].create({
            'name': 'Norwegian',
            'code': 'nb_NO',
            'iso_code': 'no',
            'url_code': 'no',
        })
        
        # Set website language
        self.website.language_ids = [(6, 0, [norwegian_lang.id])]
        
        # Create order in Norwegian context
        norwegian_order = self.env['sale.order'].with_context(lang='nb_NO').create({
            'partner_id': self.customer.id,
            'website_id': self.website.id,
            'order_line': [
                (0, 0, {
                    'product_id': self.product_a.id,
                    'product_uom_qty': 1,
                    'price_unit': 150.0,
                }),
            ],
        })
        
        # Process payment with Norwegian locale
        payment_transaction = self.env['payment.transaction'].with_context(lang='nb_NO').create({
            'reference': norwegian_order.name,
            'amount': norwegian_order.amount_total,
            'currency_id': norwegian_order.currency_id.id,
            'partner_id': norwegian_order.partner_id.id,
            'provider_id': self.provider.id,
            'sale_order_ids': [(6, 0, [norwegian_order.id])],
            'state': 'done',
        })
        
        # Verify language context handling
        self.assertEqual(payment_transaction.amount, 150.0)
        # Language-specific validation would depend on implementation