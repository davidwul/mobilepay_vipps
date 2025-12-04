
import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, Mock

from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, UserError


class TestVippsSalesModuleIntegration(TransactionCase):
    """Integration tests for Vipps/MobilePay with Sales module"""
    
    def setUp(self):
        super().setUp()
        
        # Create test company
        self.company = self.env['res.company'].create({
            'name': 'Sales Integration Test Company',
            'currency_id': self.env.ref('base.NOK').id,
        })
        
        # Create payment provider
        self.provider = self.env['payment.provider'].create({
            'name': 'Vipps Sales Integration',
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
        
        # Create test customer
        self.customer = self.env['res.partner'].create({
            'name': 'Sales Test Customer',
            'email': 'sales.test@example.com',
            'phone': '+4712345678',
            'is_company': False,
        })
        
        # Create test products
        self.product_a = self.env['product.product'].create({
            'name': 'Sales Test Product A',
            'type': 'product',
            'list_price': 100.0,
            'standard_price': 50.0,
            'categ_id': self.env.ref('product.product_category_all').id,
        })
        
        self.product_b = self.env['product.product'].create({
            'name': 'Sales Test Product B',
            'type': 'service',
            'list_price': 200.0,
            'standard_price': 100.0,
            'categ_id': self.env.ref('product.product_category_all').id,
        })
        
        # Create sales team
        self.sales_team = self.env['crm.team'].create({
            'name': 'Vipps Sales Team',
            'company_id': self.company.id,
        })
        
        # Create salesperson
        self.salesperson = self.env['res.users'].create({
            'name': 'Sales Person',
            'login': 'salesperson',
            'email': 'salesperson@example.com',
            'groups_id': [(6, 0, [
                self.env.ref('sales_team.group_sale_salesman').id,
                self.env.ref('base.group_user').id,
            ])],
        })
    
    def test_sales_order_creation_with_vipps_payment(self):
        """Test creating sales order with Vipps payment integration"""
        # Create sales order
        sale_order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'company_id': self.company.id,
            'user_id': self.salesperson.id,
            'team_id': self.sales_team.id,
            'order_line': [
                (0, 0, {
                    'product_id': self.product_a.id,
                    'product_uom_qty': 2,
                    'price_unit': 100.0,
                }),
                (0, 0, {
                    'product_id': self.product_b.id,
                    'product_uom_qty': 1,
                    'price_unit': 200.0,
                }),
            ],
        })
        
        # Verify order creation
        self.assertEqual(sale_order.state, 'draft')
        self.assertEqual(sale_order.amount_total, 400.0)
        self.assertEqual(len(sale_order.order_line), 2)
        
        # Confirm sales order
        sale_order.action_confirm()
        self.assertEqual(sale_order.state, 'sale')
        
        # Create payment transaction for the order
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
            
            # Verify payment transaction state
            self.assertEqual(payment_transaction.state, 'pending')
            
            # Simulate successful payment
            payment_transaction._set_done()
            
            # Verify integration
            self.assertEqual(payment_transaction.state, 'done')
            self.assertEqual(sale_order.invoice_status, 'to invoice')
    
    def test_sales_order_invoicing_after_payment(self):
        """Test automatic invoicing after successful Vipps payment"""
        # Create and confirm sales order
        sale_order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'company_id': self.company.id,
            'order_line': [
                (0, 0, {
                    'product_id': self.product_a.id,
                    'product_uom_qty': 1,
                    'price_unit': 100.0,
                }),
            ],
        })
        sale_order.action_confirm()
        
        # Create and process payment
        payment_transaction = self.env['payment.transaction'].create({
            'reference': sale_order.name,
            'amount': sale_order.amount_total,
            'currency_id': sale_order.currency_id.id,
            'partner_id': sale_order.partner_id.id,
            'provider_id': self.provider.id,
            'sale_order_ids': [(6, 0, [sale_order.id])],
            'state': 'done',
        })
        
        # Trigger invoice creation
        with patch.object(sale_order, '_create_invoices') as mock_create_invoices:
            mock_invoice = self.env['account.move'].create({
                'move_type': 'out_invoice',
                'partner_id': self.customer.id,
                'invoice_line_ids': [
                    (0, 0, {
                        'product_id': self.product_a.id,
                        'quantity': 1,
                        'price_unit': 100.0,
                    }),
                ],
            })
            mock_create_invoices.return_value = mock_invoice
            
            # Create invoice
            invoice = sale_order._create_invoices()
            
            # Verify invoice creation
            self.assertEqual(invoice.move_type, 'out_invoice')
            self.assertEqual(invoice.partner_id, self.customer)
            self.assertEqual(invoice.amount_total, 100.0)
            
            # Verify payment transaction is linked to invoice
            payment_transaction.invoice_ids = [(6, 0, [invoice.id])]
            self.assertIn(invoice, payment_transaction.invoice_ids)
    
    def test_sales_quotation_to_order_conversion(self):
        """Test converting quotation to order with Vipps payment"""
        # Create quotation
        quotation = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'company_id': self.company.id,
            'state': 'draft',
            'order_line': [
                (0, 0, {
                    'product_id': self.product_a.id,
                    'product_uom_qty': 3,
                    'price_unit': 100.0,
                }),
            ],
        })
        
        # Verify quotation state
        self.assertEqual(quotation.state, 'draft')
        
        # Send quotation to customer (simulate)
        quotation.action_quotation_send()
        self.assertEqual(quotation.state, 'sent')
        
        # Customer accepts and pays via Vipps
        with patch.object(self.provider, '_vipps_make_request') as mock_request:
            mock_request.return_value = {
                'orderId': quotation.name,
                'state': 'CREATED'
            }
            
            # Create payment transaction
            payment_transaction = self.env['payment.transaction'].create({
                'reference': quotation.name,
                'amount': quotation.amount_total,
                'currency_id': quotation.currency_id.id,
                'partner_id': quotation.partner_id.id,
                'provider_id': self.provider.id,
                'sale_order_ids': [(6, 0, [quotation.id])],
                'state': 'pending',
            })
            
            # Simulate successful payment
            payment_transaction._set_done()
            
            # Confirm quotation becomes sales order
            quotation.action_confirm()
            
            # Verify conversion
            self.assertEqual(quotation.state, 'sale')
            self.assertEqual(payment_transaction.state, 'done')
    
    def test_sales_order_cancellation_with_payment(self):
        """Test handling sales order cancellation with existing payment"""
        # Create and confirm sales order
        sale_order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'company_id': self.company.id,
            'order_line': [
                (0, 0, {
                    'product_id': self.product_a.id,
                    'product_uom_qty': 1,
                    'price_unit': 100.0,
                }),
            ],
        })
        sale_order.action_confirm()
        
        # Create successful payment
        payment_transaction = self.env['payment.transaction'].create({
            'reference': sale_order.name,
            'amount': sale_order.amount_total,
            'currency_id': sale_order.currency_id.id,
            'partner_id': sale_order.partner_id.id,
            'provider_id': self.provider.id,
            'sale_order_ids': [(6, 0, [sale_order.id])],
            'state': 'done',
        })
        
        # Attempt to cancel order
        with patch.object(self.provider, '_vipps_refund_transaction') as mock_refund:
            mock_refund.return_value = {
                'refundId': 'REFUND-001',
                'state': 'REFUNDED'
            }
            
            # Cancel order should trigger refund
            sale_order.action_cancel()
            
            # Verify order cancellation
            self.assertEqual(sale_order.state, 'cancel')
            
            # Verify refund was initiated
            mock_refund.assert_called_once()
    
    def test_sales_order_partial_delivery_payment(self):
        """Test partial delivery scenarios with Vipps payment"""
        # Create sales order with multiple products
        sale_order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'company_id': self.company.id,
            'order_line': [
                (0, 0, {
                    'product_id': self.product_a.id,
                    'product_uom_qty': 5,
                    'price_unit': 100.0,
                }),
                (0, 0, {
                    'product_id': self.product_b.id,
                    'product_uom_qty': 2,
                    'price_unit': 200.0,
                }),
            ],
        })
        sale_order.action_confirm()
        
        # Full payment upfront
        payment_transaction = self.env['payment.transaction'].create({
            'reference': sale_order.name,
            'amount': sale_order.amount_total,  # 900.0
            'currency_id': sale_order.currency_id.id,
            'partner_id': sale_order.partner_id.id,
            'provider_id': self.provider.id,
            'sale_order_ids': [(6, 0, [sale_order.id])],
            'state': 'done',
        })
        
        # Simulate partial delivery
        for line in sale_order.order_line:
            if line.product_id == self.product_a:
                line.qty_delivered = 3  # Partial delivery
            else:
                line.qty_delivered = 2  # Full delivery
        
        # Verify delivery status
        self.assertEqual(sale_order.delivery_status, 'partially_delivered')
        
        # Create partial invoice
        invoice = sale_order._create_invoices()
        
        # Verify invoice amount matches delivered quantities
        expected_amount = (3 * 100.0) + (2 * 200.0)  # 700.0
        self.assertEqual(invoice.amount_total, expected_amount)
    
    def test_sales_team_performance_with_vipps(self):
        """Test sales team performance tracking with Vipps payments"""
        # Create multiple sales orders for the team
        orders = []
        for i in range(5):
            order = self.env['sale.order'].create({
                'partner_id': self.customer.id,
                'company_id': self.company.id,
                'user_id': self.salesperson.id,
                'team_id': self.sales_team.id,
                'order_line': [
                    (0, 0, {
                        'product_id': self.product_a.id,
                        'product_uom_qty': 1,
                        'price_unit': 100.0,
                    }),
                ],
            })
            order.action_confirm()
            orders.append(order)
        
        # Create payments for all orders
        for order in orders:
            payment_transaction = self.env['payment.transaction'].create({
                'reference': order.name,
                'amount': order.amount_total,
                'currency_id': order.currency_id.id,
                'partner_id': order.partner_id.id,
                'provider_id': self.provider.id,
                'sale_order_ids': [(6, 0, [order.id])],
                'state': 'done',
            })
        
        # Verify sales team performance
        team_orders = self.env['sale.order'].search([
            ('team_id', '=', self.sales_team.id),
            ('state', '=', 'sale')
        ])
        
        self.assertEqual(len(team_orders), 5)
        
        total_revenue = sum(team_orders.mapped('amount_total'))
        self.assertEqual(total_revenue, 500.0)
        
        # Verify salesperson performance
        salesperson_orders = team_orders.filtered(
            lambda o: o.user_id == self.salesperson
        )
        self.assertEqual(len(salesperson_orders), 5)
    
    def test_sales_order_multi_currency_vipps(self):
        """Test sales orders with different currencies and Vipps"""
        # Create EUR customer
        eur_customer = self.env['res.partner'].create({
            'name': 'EUR Customer',
            'email': 'eur@example.com',
        })
        
        # Create sales order in EUR
        eur_order = self.env['sale.order'].create({
            'partner_id': eur_customer.id,
            'company_id': self.company.id,
            'currency_id': self.env.ref('base.EUR').id,
            'order_line': [
                (0, 0, {
                    'product_id': self.product_a.id,
                    'product_uom_qty': 1,
                    'price_unit': 85.0,  # EUR price
                }),
            ],
        })
        eur_order.action_confirm()
        
        # Create payment transaction (Vipps processes in NOK)
        with patch.object(self.provider, '_convert_currency') as mock_convert:
            mock_convert.return_value = 935.0  # EUR to NOK conversion
            
            payment_transaction = self.env['payment.transaction'].create({
                'reference': eur_order.name,
                'amount': 935.0,  # Converted to NOK
                'currency_id': self.env.ref('base.NOK').id,  # Vipps currency
                'partner_id': eur_order.partner_id.id,
                'provider_id': self.provider.id,
                'sale_order_ids': [(6, 0, [eur_order.id])],
                'state': 'done',
            })
            
            # Verify currency handling
            self.assertEqual(eur_order.currency_id.name, 'EUR')
            self.assertEqual(payment_transaction.currency_id.name, 'NOK')
            self.assertEqual(payment_transaction.amount, 935.0)
    
    def test_sales_order_discount_and_tax_integration(self):
        """Test sales orders with discounts and taxes with Vipps payment"""
        # Create tax
        tax = self.env['account.tax'].create({
            'name': 'VAT 25%',
            'amount': 25.0,
            'amount_type': 'percent',
            'type_tax_use': 'sale',
            'company_id': self.company.id,
        })
        
        # Create sales order with discount and tax
        sale_order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'company_id': self.company.id,
            'order_line': [
                (0, 0, {
                    'product_id': self.product_a.id,
                    'product_uom_qty': 2,
                    'price_unit': 100.0,
                    'discount': 10.0,  # 10% discount
                    'tax_id': [(6, 0, [tax.id])],
                }),
            ],
        })
        
        # Verify calculations
        line = sale_order.order_line[0]
        self.assertEqual(line.price_subtotal, 180.0)  # (2 * 100 * 0.9)
        self.assertEqual(sale_order.amount_untaxed, 180.0)
        self.assertEqual(sale_order.amount_tax, 45.0)  # 180 * 0.25
        self.assertEqual(sale_order.amount_total, 225.0)
        
        sale_order.action_confirm()
        
        # Create payment for total amount including tax
        payment_transaction = self.env['payment.transaction'].create({
            'reference': sale_order.name,
            'amount': sale_order.amount_total,
            'currency_id': sale_order.currency_id.id,
            'partner_id': sale_order.partner_id.id,
            'provider_id': self.provider.id,
            'sale_order_ids': [(6, 0, [sale_order.id])],
            'state': 'done',
        })
        
        # Verify payment amount matches order total
        self.assertEqual(payment_transaction.amount, 225.0)
    
    def test_sales_order_delivery_integration(self):
        """Test sales order delivery integration with Vipps payment"""
        # Create sales order
        sale_order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'company_id': self.company.id,
            'order_line': [
                (0, 0, {
                    'product_id': self.product_a.id,
                    'product_uom_qty': 3,
                    'price_unit': 100.0,
                }),
            ],
        })
        sale_order.action_confirm()
        
        # Create payment
        payment_transaction = self.env['payment.transaction'].create({
            'reference': sale_order.name,
            'amount': sale_order.amount_total,
            'currency_id': sale_order.currency_id.id,
            'partner_id': sale_order.partner_id.id,
            'provider_id': self.provider.id,
            'sale_order_ids': [(6, 0, [sale_order.id])],
            'state': 'done',
        })
        
        # Verify delivery order creation
        delivery_orders = self.env['stock.picking'].search([
            ('origin', '=', sale_order.name)
        ])
        
        if delivery_orders:
            delivery_order = delivery_orders[0]
            
            # Simulate delivery
            for move in delivery_order.move_lines:
                move.quantity_done = move.product_uom_qty
            
            delivery_order.action_done()
            
            # Verify delivery status in sales order
            self.assertEqual(sale_order.delivery_status, 'fully_delivered')
    
    def test_sales_order_return_and_refund(self):
        """Test sales order returns and refunds with Vipps"""
        # Create and process sales order
        sale_order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'company_id': self.company.id,
            'order_line': [
                (0, 0, {
                    'product_id': self.product_a.id,
                    'product_uom_qty': 2,
                    'price_unit': 100.0,
                }),
            ],
        })
        sale_order.action_confirm()
        
        # Create payment
        payment_transaction = self.env['payment.transaction'].create({
            'reference': sale_order.name,
            'amount': sale_order.amount_total,
            'currency_id': sale_order.currency_id.id,
            'partner_id': sale_order.partner_id.id,
            'provider_id': self.provider.id,
            'sale_order_ids': [(6, 0, [sale_order.id])],
            'state': 'done',
        })
        
        # Create return order
        return_order = self.env['sale.order'].create({
            'partner_id': self.customer.id,
            'company_id': self.company.id,
            'origin': sale_order.name,
            'order_line': [
                (0, 0, {
                    'product_id': self.product_a.id,
                    'product_uom_qty': -1,  # Return 1 item
                    'price_unit': 100.0,
                }),
            ],
        })
        
        # Process refund
        with patch.object(self.provider, '_vipps_refund_transaction') as mock_refund:
            mock_refund.return_value = {
                'refundId': 'REFUND-001',
                'state': 'REFUNDED',
                'amount': 100.0
            }
            
            # Create refund transaction
            refund_transaction = self.env['payment.transaction'].create({
                'reference': f'REFUND-{sale_order.name}',
                'amount': -100.0,  # Negative for refund
                'currency_id': sale_order.currency_id.id,
                'partner_id': sale_order.partner_id.id,
                'provider_id': self.provider.id,
                'source_transaction_id': payment_transaction.id,
                'state': 'done',
            })
            
            # Verify refund processing
            self.assertEqual(refund_transaction.amount, -100.0)
            self.assertEqual(refund_transaction.source_transaction_id, payment_transaction)
            mock_refund.assert_called_once()
    
    def test_sales_analytics_with_vipps_payments(self):
        """Test sales analytics integration with Vipps payment data"""
        # Create multiple sales orders with different scenarios
        orders_data = [
            {'qty': 1, 'price': 100.0, 'state': 'done'},
            {'qty': 2, 'price': 150.0, 'state': 'done'},
            {'qty': 1, 'price': 200.0, 'state': 'pending'},
            {'qty': 3, 'price': 75.0, 'state': 'done'},
        ]
        
        orders = []
        transactions = []
        
        for i, data in enumerate(orders_data):
            order = self.env['sale.order'].create({
                'partner_id': self.customer.id,
                'company_id': self.company.id,
                'user_id': self.salesperson.id,
                'team_id': self.sales_team.id,
                'order_line': [
                    (0, 0, {
                        'product_id': self.product_a.id,
                        'product_uom_qty': data['qty'],
                        'price_unit': data['price'],
                    }),
                ],
            })
            order.action_confirm()
            orders.append(order)
            
            # Create payment transaction
            transaction = self.env['payment.transaction'].create({
                'reference': order.name,
                'amount': order.amount_total,
                'currency_id': order.currency_id.id,
                'partner_id': order.partner_id.id,
                'provider_id': self.provider.id,
                'sale_order_ids': [(6, 0, [order.id])],
                'state': data['state'],
            })
            transactions.append(transaction)
        
        # Analyze sales performance
        total_orders = len(orders)
        successful_payments = len([t for t in transactions if t.state == 'done'])
        total_revenue = sum(o.amount_total for o in orders if any(
            t.state == 'done' for t in transactions if order.name in t.reference
        ))
        
        # Verify analytics
        self.assertEqual(total_orders, 4)
        self.assertEqual(successful_payments, 3)
        self.assertEqual(total_revenue, 625.0)  # 100 + 300 + 225
        
        # Payment method analysis
        vipps_transactions = self.env['payment.transaction'].search([
            ('provider_id', '=', self.provider.id),
            ('state', '=', 'done')
        ])
        
        vipps_revenue = sum(vipps_transactions.mapped('amount'))
        self.assertEqual(len(vipps_transactions), 3)
        self.assertEqual(vipps_revenue, 625.0)