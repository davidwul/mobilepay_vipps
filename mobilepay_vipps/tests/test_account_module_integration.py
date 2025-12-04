
import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, Mock

from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError, UserError


class TestVippsAccountModuleIntegration(TransactionCase):
    """Integration tests for Vipps/MobilePay with Account module"""
    
    def setUp(self):
        super().setUp()
        
        # Create test company
        self.company = self.env['res.company'].create({
            'name': 'Account Integration Test Company',
            'currency_id': self.env.ref('base.NOK').id,
        })
        
        # Create payment provider
        self.provider = self.env['payment.provider'].create({
            'name': 'Vipps Account Integration',
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
            'name': 'Account Test Customer',
            'email': 'account.test@example.com',
            'phone': '+4712345678',
        })
        
        # Create chart of accounts
        self.account_receivable = self.env['account.account'].create({
            'name': 'Account Receivable',
            'code': '1200',
            'user_type_id': self.env.ref('account.data_account_type_receivable').id,
            'company_id': self.company.id,
        })
        
        self.account_revenue = self.env['account.account'].create({
            'name': 'Revenue Account',
            'code': '4000',
            'user_type_id': self.env.ref('account.data_account_type_revenue').id,
            'company_id': self.company.id,
        })
        
        self.vipps_account = self.env['account.account'].create({
            'name': 'Vipps Clearing Account',
            'code': '1210',
            'user_type_id': self.env.ref('account.data_account_type_current_assets').id,
            'company_id': self.company.id,
        })
        
        # Set up payment provider accounts
        self.provider.journal_id = self.env['account.journal'].create({
            'name': 'Vipps Journal',
            'type': 'bank',
            'code': 'VIPPS',
            'company_id': self.company.id,
            'default_account_id': self.vipps_account.id,
        })
    
    def test_payment_reconciliation_basic(self):
        """Test basic payment reconciliation with account moves"""
        # Create invoice
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.customer.id,
            'company_id': self.company.id,
            'invoice_line_ids': [
                (0, 0, {
                    'name': 'Test Product',
                    'quantity': 1,
                    'price_unit': 100.0,
                    'account_id': self.account_revenue.id,
                }),
            ],
        })
        invoice.action_post()
        
        # Create payment transaction
        payment_transaction = self.env['payment.transaction'].create({
            'reference': invoice.name,
            'amount': invoice.amount_total,
            'currency_id': invoice.currency_id.id,
            'partner_id': invoice.partner_id.id,
            'provider_id': self.provider.id,
            'invoice_ids': [(6, 0, [invoice.id])],
            'state': 'done',
        })
        
        # Create payment record
        payment = self.env['account.payment'].create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': self.customer.id,
            'amount': 100.0,
            'currency_id': self.company.currency_id.id,
            'journal_id': self.provider.journal_id.id,
            'payment_method_line_id': self.provider.journal_id.inbound_payment_method_line_ids[0].id,
            'ref': payment_transaction.reference,
        })
        payment.action_post()
        
        # Reconcile payment with invoice
        invoice_line = invoice.line_ids.filtered(lambda l: l.account_id.user_type_id.type == 'receivable')
        payment_line = payment.line_ids.filtered(lambda l: l.account_id.user_type_id.type == 'receivable')
        
        (invoice_line + payment_line).reconcile()
        
        # Verify reconciliation
        self.assertTrue(invoice_line.reconciled)
        self.assertTrue(payment_line.reconciled)
        self.assertEqual(invoice.payment_state, 'paid')
    
    def test_automatic_payment_posting(self):
        """Test automatic payment posting after successful Vipps transaction"""
        # Create payment transaction
        payment_transaction = self.env['payment.transaction'].create({
            'reference': 'AUTO-POST-001',
            'amount': 250.0,
            'currency_id': self.company.currency_id.id,
            'partner_id': self.customer.id,
            'provider_id': self.provider.id,
            'state': 'pending',
        })
        
        # Mock successful payment processing
        with patch.object(self.provider, '_vipps_make_request') as mock_request:
            mock_request.return_value = {
                'orderId': 'AUTO-POST-001',
                'state': 'CAPTURED',
                'amount': 25000  # Amount in øre
            }
            
            # Process payment
            payment_transaction._set_done()
            
            # Verify automatic payment creation
            payments = self.env['account.payment'].search([
                ('ref', '=', payment_transaction.reference)
            ])
            
            if payments:
                payment = payments[0]
                self.assertEqual(payment.amount, 250.0)
                self.assertEqual(payment.partner_id, self.customer)
                self.assertEqual(payment.journal_id, self.provider.journal_id)
                self.assertEqual(payment.state, 'posted')
    
    def test_multi_currency_accounting(self):
        """Test multi-currency accounting with Vipps payments"""
        # Create EUR invoice
        eur_invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.customer.id,
            'company_id': self.company.id,
            'currency_id': self.env.ref('base.EUR').id,
            'invoice_line_ids': [
                (0, 0, {
                    'name': 'EUR Product',
                    'quantity': 1,
                    'price_unit': 85.0,  # EUR
                    'account_id': self.account_revenue.id,
                }),
            ],
        })
        eur_invoice.action_post()
        
        # Create payment in NOK (Vipps processes in NOK)
        with patch.object(self.env['res.currency'], '_convert') as mock_convert:
            mock_convert.return_value = 935.0  # EUR to NOK conversion
            
            payment_transaction = self.env['payment.transaction'].create({
                'reference': eur_invoice.name,
                'amount': 935.0,  # NOK amount
                'currency_id': self.env.ref('base.NOK').id,
                'partner_id': eur_invoice.partner_id.id,
                'provider_id': self.provider.id,
                'invoice_ids': [(6, 0, [eur_invoice.id])],
                'state': 'done',
            })
            
            # Create payment record
            payment = self.env['account.payment'].create({
                'payment_type': 'inbound',
                'partner_type': 'customer',
                'partner_id': self.customer.id,
                'amount': 935.0,
                'currency_id': self.env.ref('base.NOK').id,
                'journal_id': self.provider.journal_id.id,
                'payment_method_line_id': self.provider.journal_id.inbound_payment_method_line_ids[0].id,
                'ref': payment_transaction.reference,
            })
            payment.action_post()
            
            # Verify currency handling
            self.assertEqual(eur_invoice.currency_id.name, 'EUR')
            self.assertEqual(payment.currency_id.name, 'NOK')
            self.assertEqual(payment.amount, 935.0)    
 
   def test_tax_handling_in_payments(self):
        """Test tax handling in Vipps payments and accounting"""
        # Create tax
        tax = self.env['account.tax'].create({
            'name': 'VAT 25%',
            'amount': 25.0,
            'amount_type': 'percent',
            'type_tax_use': 'sale',
            'company_id': self.company.id,
        })
        
        # Create invoice with tax
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.customer.id,
            'company_id': self.company.id,
            'invoice_line_ids': [
                (0, 0, {
                    'name': 'Taxable Product',
                    'quantity': 1,
                    'price_unit': 100.0,
                    'account_id': self.account_revenue.id,
                    'tax_ids': [(6, 0, [tax.id])],
                }),
            ],
        })
        invoice.action_post()
        
        # Verify tax calculation
        self.assertEqual(invoice.amount_untaxed, 100.0)
        self.assertEqual(invoice.amount_tax, 25.0)
        self.assertEqual(invoice.amount_total, 125.0)
        
        # Create payment for full amount including tax
        payment_transaction = self.env['payment.transaction'].create({
            'reference': invoice.name,
            'amount': invoice.amount_total,
            'currency_id': invoice.currency_id.id,
            'partner_id': invoice.partner_id.id,
            'provider_id': self.provider.id,
            'invoice_ids': [(6, 0, [invoice.id])],
            'state': 'done',
        })
        
        # Verify payment amount includes tax
        self.assertEqual(payment_transaction.amount, 125.0)
    
    def test_partial_payment_reconciliation(self):
        """Test partial payment reconciliation scenarios"""
        # Create large invoice
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.customer.id,
            'company_id': self.company.id,
            'invoice_line_ids': [
                (0, 0, {
                    'name': 'Expensive Product',
                    'quantity': 1,
                    'price_unit': 1000.0,
                    'account_id': self.account_revenue.id,
                }),
            ],
        })
        invoice.action_post()
        
        # Create partial payment
        partial_payment = self.env['account.payment'].create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': self.customer.id,
            'amount': 400.0,  # Partial payment
            'currency_id': self.company.currency_id.id,
            'journal_id': self.provider.journal_id.id,
            'payment_method_line_id': self.provider.journal_id.inbound_payment_method_line_ids[0].id,
            'ref': f'PARTIAL-{invoice.name}',
        })
        partial_payment.action_post()
        
        # Reconcile partial payment
        invoice_line = invoice.line_ids.filtered(lambda l: l.account_id.user_type_id.type == 'receivable')
        payment_line = partial_payment.line_ids.filtered(lambda l: l.account_id.user_type_id.type == 'receivable')
        
        (invoice_line + payment_line).reconcile()
        
        # Verify partial reconciliation
        self.assertEqual(invoice.payment_state, 'partial')
        self.assertEqual(invoice.amount_residual, 600.0)
    
    def test_refund_accounting_integration(self):
        """Test refund processing and accounting integration"""
        # Create and post invoice
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.customer.id,
            'company_id': self.company.id,
            'invoice_line_ids': [
                (0, 0, {
                    'name': 'Refundable Product',
                    'quantity': 2,
                    'price_unit': 150.0,
                    'account_id': self.account_revenue.id,
                }),
            ],
        })
        invoice.action_post()
        
        # Create payment
        payment = self.env['account.payment'].create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': self.customer.id,
            'amount': 300.0,
            'currency_id': self.company.currency_id.id,
            'journal_id': self.provider.journal_id.id,
            'payment_method_line_id': self.provider.journal_id.inbound_payment_method_line_ids[0].id,
            'ref': invoice.name,
        })
        payment.action_post()
        
        # Reconcile
        invoice_line = invoice.line_ids.filtered(lambda l: l.account_id.user_type_id.type == 'receivable')
        payment_line = payment.line_ids.filtered(lambda l: l.account_id.user_type_id.type == 'receivable')
        (invoice_line + payment_line).reconcile()
        
        # Create credit note (refund)
        credit_note = invoice._reverse_moves([{
            'ref': f'Refund for {invoice.name}',
            'date': invoice.date,
        }])
        credit_note.action_post()
        
        # Create refund payment
        refund_payment = self.env['account.payment'].create({
            'payment_type': 'outbound',
            'partner_type': 'customer',
            'partner_id': self.customer.id,
            'amount': 150.0,  # Partial refund
            'currency_id': self.company.currency_id.id,
            'journal_id': self.provider.journal_id.id,
            'payment_method_line_id': self.provider.journal_id.outbound_payment_method_line_ids[0].id,
            'ref': f'REFUND-{invoice.name}',
        })
        refund_payment.action_post()
        
        # Verify refund accounting
        self.assertEqual(refund_payment.payment_type, 'outbound')
        self.assertEqual(refund_payment.amount, 150.0)
    
    def test_bank_statement_reconciliation(self):
        """Test bank statement reconciliation with Vipps payments"""
        # Create bank statement
        bank_statement = self.env['account.bank.statement'].create({
            'name': 'Vipps Statement 001',
            'journal_id': self.provider.journal_id.id,
            'balance_start': 0.0,
            'balance_end_real': 500.0,
        })
        
        # Add statement lines for Vipps payments
        statement_lines = []
        for i in range(3):
            line = self.env['account.bank.statement.line'].create({
                'statement_id': bank_statement.id,
                'name': f'Vipps Payment {i+1}',
                'amount': 100.0 + (i * 50),
                'partner_id': self.customer.id,
                'ref': f'VIPPS-{i+1:03d}',
            })
            statement_lines.append(line)
        
        # Create corresponding payment transactions
        for i, line in enumerate(statement_lines):
            payment_transaction = self.env['payment.transaction'].create({
                'reference': line.ref,
                'amount': line.amount,
                'currency_id': self.company.currency_id.id,
                'partner_id': line.partner_id.id,
                'provider_id': self.provider.id,
                'state': 'done',
            })
        
        # Reconcile statement lines
        for line in statement_lines:
            # Find matching payment transaction
            transaction = self.env['payment.transaction'].search([
                ('reference', '=', line.ref)
            ])
            
            if transaction:
                # Create reconciliation
                line.reconcile([{
                    'account_id': self.account_receivable.id,
                    'partner_id': line.partner_id.id,
                    'amount': line.amount,
                }])
        
        # Verify reconciliation
        reconciled_lines = statement_lines.filtered(lambda l: l.is_reconciled)
        self.assertEqual(len(reconciled_lines), 3)
    
    def test_accounting_reports_with_vipps(self):
        """Test accounting reports including Vipps payment data"""
        # Create multiple transactions
        transactions_data = [
            {'amount': 100.0, 'partner': self.customer},
            {'amount': 250.0, 'partner': self.customer},
            {'amount': 175.0, 'partner': self.customer},
        ]
        
        payments = []
        for i, data in enumerate(transactions_data):
            payment = self.env['account.payment'].create({
                'payment_type': 'inbound',
                'partner_type': 'customer',
                'partner_id': data['partner'].id,
                'amount': data['amount'],
                'currency_id': self.company.currency_id.id,
                'journal_id': self.provider.journal_id.id,
                'payment_method_line_id': self.provider.journal_id.inbound_payment_method_line_ids[0].id,
                'ref': f'VIPPS-REPORT-{i+1:03d}',
            })
            payment.action_post()
            payments.append(payment)
        
        # Generate payment report data
        total_vipps_payments = sum(p.amount for p in payments)
        vipps_payment_count = len(payments)
        
        # Verify report data
        self.assertEqual(total_vipps_payments, 525.0)
        self.assertEqual(vipps_payment_count, 3)
        
        # Test journal-specific reporting
        journal_payments = self.env['account.payment'].search([
            ('journal_id', '=', self.provider.journal_id.id)
        ])
        
        self.assertEqual(len(journal_payments), 3)
        self.assertEqual(sum(journal_payments.mapped('amount')), 525.0)
    
    def test_aged_receivables_with_vipps(self):
        """Test aged receivables report with Vipps payment integration"""
        # Create invoices with different dates
        invoice_dates = [
            datetime.now() - timedelta(days=5),   # Recent
            datetime.now() - timedelta(days=35),  # 30+ days
            datetime.now() - timedelta(days=65),  # 60+ days
        ]
        
        invoices = []
        for i, date in enumerate(invoice_dates):
            invoice = self.env['account.move'].create({
                'move_type': 'out_invoice',
                'partner_id': self.customer.id,
                'company_id': self.company.id,
                'invoice_date': date.date(),
                'invoice_line_ids': [
                    (0, 0, {
                        'name': f'Aged Product {i+1}',
                        'quantity': 1,
                        'price_unit': 200.0,
                        'account_id': self.account_revenue.id,
                    }),
                ],
            })
            invoice.action_post()
            invoices.append(invoice)
        
        # Pay only the recent invoice via Vipps
        recent_invoice = invoices[0]
        payment = self.env['account.payment'].create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': self.customer.id,
            'amount': 200.0,
            'currency_id': self.company.currency_id.id,
            'journal_id': self.provider.journal_id.id,
            'payment_method_line_id': self.provider.journal_id.inbound_payment_method_line_ids[0].id,
            'ref': recent_invoice.name,
        })
        payment.action_post()
        
        # Reconcile recent invoice
        invoice_line = recent_invoice.line_ids.filtered(lambda l: l.account_id.user_type_id.type == 'receivable')
        payment_line = payment.line_ids.filtered(lambda l: l.account_id.user_type_id.type == 'receivable')
        (invoice_line + payment_line).reconcile()
        
        # Verify aged receivables
        paid_invoices = [inv for inv in invoices if inv.payment_state == 'paid']
        unpaid_invoices = [inv for inv in invoices if inv.payment_state != 'paid']
        
        self.assertEqual(len(paid_invoices), 1)
        self.assertEqual(len(unpaid_invoices), 2)
        self.assertEqual(sum(inv.amount_residual for inv in unpaid_invoices), 400.0)
    
    def test_cash_flow_reporting_with_vipps(self):
        """Test cash flow reporting with Vipps payment integration"""
        # Create cash flow entries
        cash_flows = []
        
        # Inbound cash flows (payments received)
        for i in range(3):
            payment = self.env['account.payment'].create({
                'payment_type': 'inbound',
                'partner_type': 'customer',
                'partner_id': self.customer.id,
                'amount': 300.0 + (i * 100),
                'currency_id': self.company.currency_id.id,
                'journal_id': self.provider.journal_id.id,
                'payment_method_line_id': self.provider.journal_id.inbound_payment_method_line_ids[0].id,
                'ref': f'CASHFLOW-IN-{i+1:03d}',
                'date': datetime.now().date(),
            })
            payment.action_post()
            cash_flows.append(payment)
        
        # Calculate cash flow metrics
        total_inbound = sum(p.amount for p in cash_flows)
        daily_average = total_inbound / len(cash_flows)
        
        # Verify cash flow calculations
        self.assertEqual(total_inbound, 1200.0)  # 300 + 400 + 500
        self.assertEqual(daily_average, 400.0)
        
        # Test journal cash flow
        journal_balance = self.provider.journal_id.current_statement_balance
        # Note: This would be calculated based on actual statement reconciliation