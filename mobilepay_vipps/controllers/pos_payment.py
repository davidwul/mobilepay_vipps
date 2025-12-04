
import json
import logging
from datetime import datetime
from odoo import http, _
from odoo.http import request
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class VippsPOSController(http.Controller):
    """Controller for Vipps POS payment operations"""

    @http.route('/pos/vipps/get_payment_config', type='json', auth='user', methods=['POST'])
    def get_payment_config(self, **kwargs):
        """Get POS payment method configuration"""
        try:
            # Validate user has POS access
            if not request.env.user.has_group('point_of_sale.group_pos_user'):
                return {
                    'success': False,
                    'error': _('Access denied: POS user rights required')
                }

            # Get the Vipps payment method for current session
            pos_session_id = kwargs.get('pos_session_id')
            if pos_session_id:
                pos_session = request.env['pos.session'].browse(pos_session_id)
                payment_methods = pos_session.config_id.payment_method_ids.filtered(
                    lambda pm: pm.use_payment_terminal == 'vipps'
                )
            else:
                # Fallback to any Vipps payment method
                payment_methods = request.env['pos.payment.method'].search([
                    ('use_payment_terminal', '=', 'vipps')
                ], limit=1)

            if not payment_methods:
                return {
                    'success': False,
                    'error': _('No Vipps payment method configured')
                }

            payment_method = payment_methods[0]
            provider = payment_method.payment_provider_id

            return {
                'success': True,
                'timeout': provider.vipps_payment_timeout or 300,
                'polling_interval': provider.vipps_polling_interval or 2,
                'payment_method': {
                    'id': payment_method.id,
                    'name': payment_method.name,
                    'vipps_enable_qr_flow': provider.vipps_enable_qr_flow,
                    'vipps_enable_phone_flow': provider.vipps_enable_phone_flow,
                    'vipps_enable_manual_flows': provider.vipps_enable_manual_flows,
                }
            }

        except Exception as e:
            _logger.error("Failed to get payment config: %s", str(e))
            return {
                'success': False,
                'error': _('Failed to load payment configuration')
            }

    @http.route('/pos/vipps/create_payment', type='json', auth='user', methods=['POST'])
    def create_pos_payment(self, **kwargs):
        """Create a new POS payment transaction"""
        try:
            # Validate user has POS access
            if not request.env.user.has_group('point_of_sale.group_pos_user'):
                return {
                    'success': False,
                    'error': _('Access denied: POS user rights required')
                }

            # Extract payment data
            payment_data = kwargs.get('payment_data', {})
            required_fields = ['amount', 'currency', 'reference', 'flow']
            
            for field in required_fields:
                if not payment_data.get(field):
                    return {
                        'success': False,
                        'error': _('Missing required field: %s') % field
                    }

            # Validate POS session
            pos_session_id = payment_data.get('pos_session_id')
            if pos_session_id:
                pos_session = request.env['pos.session'].sudo().browse(pos_session_id)
                if not pos_session.exists() or pos_session.state != 'opened':
                    return {
                        'success': False,
                        'error': _('Invalid or closed POS session')
                    }

            # Get payment method
            payment_methods = request.env['pos.payment.method'].search([
                ('use_payment_terminal', '=', 'vipps')
            ], limit=1)
            
            if not payment_methods:
                return {
                    'success': False,
                    'error': _('Vipps payment method not found')
                }

            payment_method = payment_methods[0]
            provider = payment_method.payment_provider_id

            # Validate phone number for phone flow
            if payment_data['flow'] == 'customer_phone':
                phone = payment_data.get('customer_phone', '').strip()
                if not phone:
                    return {
                        'success': False,
                        'error': _('Phone number is required for phone payment flow')
                    }
                
                # Validate Nordic phone number format
                import re
                phone_pattern = r'^(\+47|\+45|0047|0045)?\s?[0-9]{8}$'
                if not re.match(phone_pattern, phone.replace(' ', '')):
                    return {
                        'success': False,
                        'error': _('Invalid Nordic phone number format')
                    }

            # Create payment transaction
            transaction_vals = {
                'provider_id': provider.id,
                'reference': payment_data['reference'],
                'amount': payment_data['amount'],
                'currency_id': request.env['res.currency'].search([
                    ('name', '=', payment_data['currency'])
                ], limit=1).id,
                'partner_id': request.env.user.partner_id.id,
                'operation': 'online_direct',
                'vipps_payment_flow': payment_data['flow'],
                'vipps_customer_phone': payment_data.get('customer_phone', ''),
                'pos_session_id': pos_session_id,
            }

            transaction = request.env['payment.transaction'].sudo().create(transaction_vals)

            # Process payment based on flow
            if payment_data['flow'] == 'customer_qr':
                result = transaction._vipps_create_qr_payment()
            elif payment_data['flow'] == 'customer_phone':
                result = transaction._vipps_create_phone_payment()
            elif payment_data['flow'] == 'manual_shop_number':
                result = transaction._vipps_create_manual_payment('shop_number')
            elif payment_data['flow'] == 'manual_shop_qr':
                result = transaction._vipps_create_manual_payment('shop_qr')
            else:
                return {
                    'success': False,
                    'error': _('Unsupported payment flow: %s') % payment_data['flow']
                }

            if result.get('success'):
                return {
                    'success': True,
                    'transaction_id': transaction.id,
                    'reference': transaction.reference,
                    'qr_code': result.get('qr_code'),
                    'shop_number': result.get('shop_number'),
                    'shop_qr_code': result.get('shop_qr_code'),
                    'deeplink_url': result.get('deeplink_url'),
                }
            else:
                return {
                    'success': False,
                    'error': result.get('error', _('Payment creation failed'))
                }

        except Exception as e:
            _logger.error("POS payment creation failed: %s", str(e))
            return {
                'success': False,
                'error': _('Payment creation failed: %s') % str(e)
            }

    @http.route('/pos/vipps/poll_status', type='json', auth='user', methods=['POST'])
    def poll_payment_status(self, **kwargs):
        """Enhanced payment transaction status polling with monitoring data"""
        try:
            # Validate user has POS access
            if not request.env.user.has_group('point_of_sale.group_pos_user'):
                return {
                    'success': False,
                    'error': _('Access denied: POS user rights required')
                }

            transaction_id = kwargs.get('transaction_id')
            if not transaction_id:
                return {
                    'success': False,
                    'error': _('Transaction ID is required')
                }

            transaction = request.env['payment.transaction'].sudo().browse(transaction_id)
            if not transaction.exists():
                return {
                    'success': False,
                    'error': _('Transaction not found')
                }

            # Check current status with enhanced monitoring
            status_result = transaction._vipps_check_payment_status()
            
            # Calculate processing time
            create_date = transaction.create_date
            processing_time = 0
            if create_date:
                from datetime import datetime
                processing_time = int((datetime.now() - create_date).total_seconds())

            # Get additional monitoring data
            monitoring_data = {
                'last_status_check': transaction.vipps_last_status_check.isoformat() if transaction.vipps_last_status_check else None,
                'processing_time': processing_time,
                'retry_count': getattr(transaction, '_retry_count', 0),
                'webhook_received': transaction.vipps_webhook_received,
                'payment_state': transaction.vipps_payment_state,
                'connection_quality': self._assess_connection_quality(transaction),
            }

            return {
                'success': True,
                'status': transaction.state,
                'vipps_status': transaction.vipps_payment_state,
                'transaction_id': transaction.id,
                'reference': transaction.reference,
                'amount': transaction.amount,
                'currency': transaction.currency_id.name,
                'monitoring': monitoring_data,
                'error': transaction.state_message if transaction.state in ['error', 'cancel'] else None,
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            _logger.error("Enhanced status polling failed: %s", str(e))
            return {
                'success': False,
                'error': _('Status check failed: %s') % str(e),
                'timestamp': datetime.now().isoformat()
            }

    def _assess_connection_quality(self, transaction):
        """Assess connection quality based on transaction history"""
        try:
            # Simple connection quality assessment
            if transaction.vipps_last_status_check:
                from datetime import datetime, timedelta
                last_check = transaction.vipps_last_status_check
                time_since_check = datetime.now() - last_check
                
                if time_since_check < timedelta(seconds=10):
                    return 'excellent'
                elif time_since_check < timedelta(seconds=30):
                    return 'good'
                elif time_since_check < timedelta(minutes=2):
                    return 'fair'
                else:
                    return 'poor'
            
            return 'unknown'
        except:
            return 'unknown'

    @http.route('/pos/vipps/cancel_payment', type='json', auth='user', methods=['POST'])
    def cancel_payment(self, **kwargs):
        """Cancel a payment transaction"""
        try:
            # Validate user has POS access
            if not request.env.user.has_group('point_of_sale.group_pos_user'):
                return {
                    'success': False,
                    'error': _('Access denied: POS user rights required')
                }

            transaction_id = kwargs.get('transaction_id')
            if not transaction_id:
                return {
                    'success': False,
                    'error': _('Transaction ID is required')
                }

            transaction = request.env['payment.transaction'].sudo().browse(transaction_id)
            if not transaction.exists():
                return {
                    'success': False,
                    'error': _('Transaction not found')
                }

            # Cancel the payment
            result = transaction._vipps_cancel_payment()
            
            if result.get('success'):
                return {
                    'success': True,
                    'transaction_id': transaction.id,
                    'status': transaction.state
                }
            else:
                return {
                    'success': False,
                    'error': result.get('error', _('Payment cancellation failed'))
                }

        except Exception as e:
            _logger.error("Payment cancellation failed: %s", str(e))
            return {
                'success': False,
                'error': _('Cancellation failed: %s') % str(e)
            }

    @http.route('/pos/vipps/verify_manual_payment', type='json', auth='user', methods=['POST'])
    def verify_manual_payment(self, **kwargs):
        """Verify manual payment completion"""
        try:
            # Validate user has POS access
            if not request.env.user.has_group('point_of_sale.group_pos_user'):
                return {
                    'success': False,
                    'error': _('Access denied: POS user rights required')
                }

            transaction_id = kwargs.get('transaction_id')
            if not transaction_id:
                return {
                    'success': False,
                    'error': _('Transaction ID is required')
                }

            transaction = request.env['payment.transaction'].sudo().browse(transaction_id)
            if not transaction.exists():
                return {
                    'success': False,
                    'error': _('Transaction not found')
                }

            # For manual payments, we need to check the actual payment status
            # This would typically involve checking with Vipps API
            result = transaction._vipps_verify_manual_payment()
            
            return {
                'success': True,
                'status': transaction.state,
                'verified': result.get('verified', False),
                'payment_details': result.get('payment_details', {})
            }

        except Exception as e:
            _logger.error("Manual payment verification failed: %s", str(e))
            return {
                'success': False,
                'error': _('Verification failed: %s') % str(e)
            }

    @http.route('/pos/vipps/monitoring_data', type='json', auth='user', methods=['POST'])
    def get_monitoring_data(self, **kwargs):
        """Get detailed monitoring data for POS payment"""
        try:
            # Validate user has POS access
            if not request.env.user.has_group('point_of_sale.group_pos_user'):
                return {
                    'success': False,
                    'error': _('Access denied: POS user rights required')
                }

            transaction_id = kwargs.get('transaction_id')
            if not transaction_id:
                return {
                    'success': False,
                    'error': _('Transaction ID is required')
                }

            transaction = request.env['payment.transaction'].sudo().browse(transaction_id)
            if not transaction.exists():
                return {
                    'success': False,
                    'error': _('Transaction not found')
                }

            # Collect comprehensive monitoring data
            monitoring_data = {
                'transaction_info': {
                    'id': transaction.id,
                    'reference': transaction.reference,
                    'amount': transaction.amount,
                    'currency': transaction.currency_id.name,
                    'state': transaction.state,
                    'vipps_state': transaction.vipps_payment_state,
                    'created': transaction.create_date.isoformat() if transaction.create_date else None,
                },
                'timing_info': {
                    'last_status_check': transaction.vipps_last_status_check.isoformat() if transaction.vipps_last_status_check else None,
                    'processing_duration': self._calculate_processing_duration(transaction),
                    'webhook_received': transaction.vipps_webhook_received,
                },
                'technical_info': {
                    'payment_reference': transaction.vipps_payment_reference,
                    'psp_reference': transaction.vipps_psp_reference,
                    'user_flow': transaction.vipps_user_flow,
                    'payment_flow': transaction.vipps_payment_flow,
                    'idempotency_key': transaction.vipps_idempotency_key,
                },
                'status_history': self._get_status_history(transaction),
                'connection_metrics': {
                    'quality': self._assess_connection_quality(transaction),
                    'last_successful_check': transaction.vipps_last_status_check.isoformat() if transaction.vipps_last_status_check else None,
                }
            }

            return {
                'success': True,
                'monitoring_data': monitoring_data,
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            _logger.error("Failed to get monitoring data: %s", str(e))
            return {
                'success': False,
                'error': _('Failed to get monitoring data: %s') % str(e)
            }

    def _calculate_processing_duration(self, transaction):
        """Calculate how long the payment has been processing"""
        if transaction.create_date:
            from datetime import datetime
            return int((datetime.now() - transaction.create_date).total_seconds())
        return 0

    def _get_status_history(self, transaction):
        """Get status change history for the transaction"""
        # In a real implementation, this would query a status history table
        # For now, we'll return basic information
        history = []
        
        if transaction.create_date:
            history.append({
                'timestamp': transaction.create_date.isoformat(),
                'status': 'created',
                'message': 'Payment transaction created'
            })
        
        if transaction.vipps_last_status_check:
            history.append({
                'timestamp': transaction.vipps_last_status_check.isoformat(),
                'status': transaction.vipps_payment_state or 'unknown',
                'message': f'Status checked: {transaction.vipps_payment_state or "unknown"}'
            })
        
        return history

    @http.route('/pos/vipps/receipt_data', type='json', auth='user', methods=['POST'])
    def get_receipt_data(self, **kwargs):
        """Get receipt data for completed payment"""
        try:
            # Validate user has POS access
            if not request.env.user.has_group('point_of_sale.group_pos_user'):
                return {
                    'success': False,
                    'error': _('Access denied: POS user rights required')
                }

            transaction_id = kwargs.get('transaction_id')
            if not transaction_id:
                return {
                    'success': False,
                    'error': _('Transaction ID is required')
                }

            transaction = request.env['payment.transaction'].sudo().browse(transaction_id)
            if not transaction.exists():
                return {
                    'success': False,
                    'error': _('Transaction not found')
                }

            # Generate receipt data
            receipt_data = {
                'header': 'VIPPS/MOBILEPAY PAYMENT',
                'lines': [
                    {'type': 'line', 'left': 'Amount:', 'right': f"{transaction.amount} {transaction.currency_id.name}"},
                    {'type': 'line', 'left': 'Method:', 'right': self._get_flow_display_name(transaction.vipps_payment_flow)},
                    {'type': 'line', 'left': 'Transaction ID:', 'right': transaction.vipps_payment_reference or transaction.reference},
                    {'type': 'line', 'left': 'Status:', 'right': transaction.vipps_payment_state or transaction.state},
                    {'type': 'line', 'left': 'Time:', 'right': datetime.now().strftime('%Y-%m-%d %H:%M:%S')},
                ],
                'footer': 'Thank you for your payment!'
            }

            # Add customer phone if available
            if transaction.vipps_customer_phone:
                receipt_data['lines'].insert(-1, {
                    'type': 'line', 
                    'left': 'Phone:', 
                    'right': transaction.vipps_customer_phone
                })

            return {
                'success': True,
                'receipt_data': receipt_data,
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            _logger.error("Failed to get receipt data: %s", str(e))
            return {
                'success': False,
                'error': _('Failed to get receipt data: %s') % str(e)
            }

    def _get_flow_display_name(self, flow_code):
        """Get display name for payment flow"""
        flow_names = {
            'customer_qr': 'Customer QR Code',
            'customer_phone': 'Phone Push Message',
            'manual_shop_number': 'Manual Shop Number',
            'manual_shop_qr': 'Manual Shop QR'
        }
        return flow_names.get(flow_code, flow_code or 'Unknown')