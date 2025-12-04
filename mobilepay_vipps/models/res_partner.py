
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import json
import logging

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Vipps user information tracking
    vipps_user_info_collected = fields.Boolean(
        string="Vipps User Info Collected",
        default=False,
        help="Whether user information has been collected from Vipps/MobilePay"
    )
    
    vipps_data_collection_count = fields.Integer(
        string="Data Collection Count",
        default=0,
        help="Number of times data was collected from Vipps/MobilePay"
    )
    
    vipps_last_data_collection = fields.Datetime(
        string="Last Data Collection",
        help="When data was last collected from Vipps/MobilePay"
    )
    
    vipps_data_consent_given = fields.Boolean(
        string="Data Collection Consent",
        default=False,
        help="Whether customer has given consent for data collection"
    )
    
    vipps_data_consent_date = fields.Datetime(
        string="Consent Date",
        help="When consent was given for data collection"
    )
    
    vipps_opt_out_date = fields.Datetime(
        string="Opt-out Date",
        help="When customer opted out of data collection"
    )

    def update_vipps_data_stats(self):
        """Update statistics about Vipps data collection (called manually)"""
        for partner in self:
            # Search for Vipps transactions for this partner
            vipps_transactions = self.env['payment.transaction'].search([
                ('partner_id', '=', partner.id),
                ('provider_code', '=', 'vipps'),
                ('vipps_user_details', '!=', False)
            ])
            
            partner.vipps_data_collection_count = len(vipps_transactions)
            
            if vipps_transactions:
                # Get the most recent collection date
                latest_transaction = max(vipps_transactions, key=lambda t: t.create_date)
                try:
                    user_data = json.loads(latest_transaction.vipps_user_details)
                    if user_data.get('collected_at'):
                        from datetime import datetime
                        partner.vipps_last_data_collection = datetime.fromisoformat(user_data['collected_at'])
                    else:
                        partner.vipps_last_data_collection = latest_transaction.create_date
                except (json.JSONDecodeError, ValueError):
                    partner.vipps_last_data_collection = latest_transaction.create_date
                
                partner.vipps_user_info_collected = True
            else:
                partner.vipps_last_data_collection = False
                partner.vipps_user_info_collected = False

    def action_view_vipps_data_collections(self):
        """View all Vipps data collections for this partner"""
        self.ensure_one()
        
        vipps_transactions = self.env['payment.transaction'].search([
            ('partner_id', '=', self.id),
            ('provider_code', '=', 'vipps'),
            ('vipps_user_details', '!=', False)
        ])
        
        if not vipps_transactions:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No Data Collections'),
                    'message': _('No Vipps/MobilePay data collections found for this customer'),
                    'type': 'info',
                }
            }
        
        return {
            'name': _('Vipps Data Collections'),
            'type': 'ir.actions.act_window',
            'res_model': 'payment.transaction',
            'view_mode': 'list,form',
            'domain': [('id', 'in', vipps_transactions.ids)],
            'context': {
                'search_default_group_by_create_date': 1,
            }
        }

    def action_export_vipps_data(self):
        """Export all collected Vipps data for GDPR compliance"""
        self.ensure_one()
        
        vipps_transactions = self.env['payment.transaction'].search([
            ('partner_id', '=', self.id),
            ('provider_code', '=', 'vipps'),
            ('vipps_user_details', '!=', False)
        ])
        
        if not vipps_transactions:
            raise ValidationError(_("No Vipps data found for this customer"))
        
        # Create audit log for data access
        self.env['vipps.data.audit.log'].log_data_action(
            partner_id=self.id,
            action_type='access',
            data_types=f'{len(vipps_transactions)} transaction records',
            legal_basis='consent',
            notes='Customer data export initiated'
        )
        
        # Collect all data
        export_data = {
            'customer_info': {
                'name': self.name,
                'email': self.email,
                'phone': self.phone,
                'export_date': fields.Datetime.now().isoformat(),
            },
            'data_collections': []
        }
        
        for transaction in vipps_transactions:
            try:
                user_data = json.loads(transaction.vipps_user_details)
                collection_record = {
                    'transaction_reference': transaction.reference,
                    'collection_date': user_data.get('collected_at'),
                    'scopes_collected': user_data.get('scopes_collected', []),
                    'data': user_data.get('data', {}),
                    'consent_given': user_data.get('consent_given', False),
                    'retention_expires': user_data.get('retention_expires'),
                }
                export_data['data_collections'].append(collection_record)
            except (json.JSONDecodeError, ValueError) as e:
                _logger.error(
                    "Error parsing user data for transaction %s: %s",
                    transaction.reference, str(e)
                )
        
        # In a real implementation, this would generate a downloadable file
        return {
            'name': _('Export Vipps Data'),
            'type': 'ir.actions.act_window',
            'res_model': 'vipps.data.export.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_partner_id': self.id,
                'default_export_data': json.dumps(export_data, indent=2),
            }
        }

    def action_delete_vipps_data(self):
        """Delete all collected Vipps data for this customer"""
        self.ensure_one()
        
        vipps_transactions = self.env['payment.transaction'].search([
            ('partner_id', '=', self.id),
            ('provider_code', '=', 'vipps'),
            ('vipps_user_details', '!=', False)
        ])
        
        if not vipps_transactions:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No Data to Delete'),
                    'message': _('No Vipps data found for this customer'),
                    'type': 'info',
                }
            }
        
        return {
            'name': _('Delete Vipps Data'),
            'type': 'ir.actions.act_window',
            'res_model': 'vipps.data.deletion.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_partner_id': self.id,
                'default_transaction_count': len(vipps_transactions),
            }
        }

    def action_opt_out_data_collection(self):
        """Opt out of future data collection"""
        self.ensure_one()
        
        self.write({
            'vipps_data_consent_given': False,
            'vipps_opt_out_date': fields.Datetime.now(),
        })
        
        # Create audit log for consent withdrawal
        self.env['vipps.data.audit.log'].log_data_action(
            partner_id=self.id,
            action_type='consent_withdrawn',
            legal_basis='consent',
            notes='Customer opted out of future data collection'
        )
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Opt-out Recorded'),
                'message': _('Customer has been opted out of future Vipps data collection'),
                'type': 'success',
            }
        }

    def action_give_data_consent(self):
        """Give consent for data collection"""
        self.ensure_one()
        
        self.write({
            'vipps_data_consent_given': True,
            'vipps_data_consent_date': fields.Datetime.now(),
            'vipps_opt_out_date': False,
        })
        
        # Create audit log for consent given
        self.env['vipps.data.audit.log'].log_data_action(
            partner_id=self.id,
            action_type='consent_given',
            legal_basis='consent',
            notes='Customer consent for data collection recorded'
        )
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Consent Recorded'),
                'message': _('Customer consent for Vipps data collection has been recorded'),
                'type': 'success',
            }
        }

    @api.model
    def _cleanup_partner_vipps_flags(self):
        """Cleanup partner flags when no more Vipps data exists"""
        partners_with_flags = self.search([
            ('vipps_user_info_collected', '=', True)
        ])
        
        for partner in partners_with_flags:
            vipps_transactions = self.env['payment.transaction'].search([
                ('partner_id', '=', partner.id),
                ('provider_code', '=', 'vipps'),
                ('vipps_user_details', '!=', False)
            ])
            
            if not vipps_transactions:
                partner.write({
                    'vipps_user_info_collected': False,
                })
                _logger.info(
                    "Cleaned up Vipps flags for partner %s (no data remaining)",
                    partner.name
                )