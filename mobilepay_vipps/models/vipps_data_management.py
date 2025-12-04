
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import json
import base64
import logging

_logger = logging.getLogger(__name__)


class VippsDataExportWizard(models.TransientModel):
    _name = 'vipps.data.export.wizard'
    _description = 'Vipps Data Export Wizard'

    partner_id = fields.Many2one(
        'res.partner',
        string="Customer",
        required=True
    )
    
    export_data = fields.Text(
        string="Export Data",
        readonly=True
    )
    
    export_format = fields.Selection([
        ('json', 'JSON Format'),
        ('csv', 'CSV Format'),
        ('pdf', 'PDF Report')
    ], string="Export Format", default='json', required=True)
    
    include_transaction_details = fields.Boolean(
        string="Include Transaction Details",
        default=True,
        help="Include payment transaction references and dates"
    )
    
    include_raw_data = fields.Boolean(
        string="Include Raw Data",
        default=False,
        help="Include raw API response data (technical details)"
    )

    def action_generate_export(self):
        """Generate the data export file"""
        self.ensure_one()
        
        if not self.export_data:
            raise ValidationError(_("No data available for export"))
        
        try:
            data = json.loads(self.export_data)
        except json.JSONDecodeError:
            raise ValidationError(_("Invalid export data format"))
        
        # Filter data based on options
        if not self.include_transaction_details:
            for collection in data.get('data_collections', []):
                collection.pop('transaction_reference', None)
        
        if not self.include_raw_data:
            for collection in data.get('data_collections', []):
                # Keep only essential fields
                essential_data = {}
                raw_data = collection.get('data', {})
                for key in ['name', 'email', 'phoneNumber', 'address']:
                    if key in raw_data:
                        essential_data[key] = raw_data[key]
                collection['data'] = essential_data
        
        # Generate file based on format
        if self.export_format == 'json':
            file_content = json.dumps(data, indent=2, ensure_ascii=False)
            filename = f"vipps_data_export_{self.partner_id.id}.json"
            mimetype = 'application/json'
        
        elif self.export_format == 'csv':
            file_content = self._generate_csv_export(data)
            filename = f"vipps_data_export_{self.partner_id.id}.csv"
            mimetype = 'text/csv'
        
        elif self.export_format == 'pdf':
            # This would generate a PDF report
            file_content = self._generate_pdf_export(data)
            filename = f"vipps_data_export_{self.partner_id.id}.pdf"
            mimetype = 'application/pdf'
        
        # Create attachment
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(file_content.encode('utf-8')),
            'res_model': 'res.partner',
            'res_id': self.partner_id.id,
            'mimetype': mimetype,
        })
        
        # Create audit log for data export
        self.env['vipps.data.audit.log'].log_data_action(
            partner_id=self.partner_id.id,
            action_type='export',
            data_types=f'Export format: {self.export_format}',
            legal_basis='consent',
            notes=f'Customer data exported in {self.export_format} format'
        )
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    def _generate_csv_export(self, data):
        """Generate CSV format export"""
        import csv
        import io
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'Customer Name', 'Customer Email', 'Customer Phone',
            'Collection Date', 'Scopes Collected', 'Consent Given',
            'Transaction Reference', 'Retention Expires'
        ])
        
        customer_info = data.get('customer_info', {})
        
        for collection in data.get('data_collections', []):
            writer.writerow([
                customer_info.get('name', ''),
                customer_info.get('email', ''),
                customer_info.get('phone', ''),
                collection.get('collection_date', ''),
                ', '.join(collection.get('scopes_collected', [])),
                collection.get('consent_given', ''),
                collection.get('transaction_reference', ''),
                collection.get('retention_expires', ''),
            ])
        
        return output.getvalue()

    def _generate_pdf_export(self, data):
        """Generate PDF format export"""
        # This would use a proper PDF generation library
        # For now, return a simple text representation
        content = f"""
VIPPS/MOBILEPAY DATA EXPORT REPORT

Customer Information:
- Name: {data.get('customer_info', {}).get('name', 'N/A')}
- Email: {data.get('customer_info', {}).get('email', 'N/A')}
- Phone: {data.get('customer_info', {}).get('phone', 'N/A')}
- Export Date: {data.get('customer_info', {}).get('export_date', 'N/A')}

Data Collections:
"""
        
        for i, collection in enumerate(data.get('data_collections', []), 1):
            content += f"""
Collection #{i}:
- Date: {collection.get('collection_date', 'N/A')}
- Scopes: {', '.join(collection.get('scopes_collected', []))}
- Consent: {collection.get('consent_given', 'N/A')}
- Transaction: {collection.get('transaction_reference', 'N/A')}
- Expires: {collection.get('retention_expires', 'Never')}
"""
        
        return content


class VippsDataDeletionWizard(models.TransientModel):
    _name = 'vipps.data.deletion.wizard'
    _description = 'Vipps Data Deletion Wizard'

    partner_id = fields.Many2one(
        'res.partner',
        string="Customer",
        required=True
    )
    
    transaction_count = fields.Integer(
        string="Transactions with Data",
        readonly=True
    )
    
    deletion_reason = fields.Selection([
        ('customer_request', 'Customer Request (GDPR)'),
        ('retention_expired', 'Retention Period Expired'),
        ('opt_out', 'Customer Opt-out'),
        ('data_correction', 'Data Correction'),
        ('other', 'Other Reason')
    ], string="Deletion Reason", required=True)
    
    deletion_notes = fields.Text(
        string="Deletion Notes",
        help="Additional notes about the deletion"
    )
    
    confirm_deletion = fields.Boolean(
        string="I confirm this deletion",
        help="Check this box to confirm you want to permanently delete the data"
    )
    
    create_audit_log = fields.Boolean(
        string="Create Audit Log",
        default=True,
        help="Create an audit log entry for this deletion"
    )

    def action_delete_data(self):
        """Perform the data deletion"""
        self.ensure_one()
        
        if not self.confirm_deletion:
            raise ValidationError(_("Please confirm the deletion by checking the confirmation box"))
        
        vipps_transactions = self.env['payment.transaction'].search([
            ('partner_id', '=', self.partner_id.id),
            ('provider_code', '=', 'vipps'),
            ('vipps_user_details', '!=', False)
        ])
        
        if not vipps_transactions:
            raise ValidationError(_("No Vipps data found for this customer"))
        
        # Create audit log before deletion if requested
        if self.create_audit_log:
            self._create_deletion_audit_log(vipps_transactions)
        
        # Create audit log entry for data deletion
        self.env['vipps.data.audit.log'].log_data_action(
            partner_id=self.partner_id.id,
            action_type='deletion',
            data_types=f'{len(vipps_transactions)} transaction records',
            legal_basis='consent',
            notes=f'Reason: {self.deletion_reason}. {self.deletion_notes or ""}'
        )
        
        # Delete the data
        deleted_count = 0
        for transaction in vipps_transactions:
            if transaction.vipps_user_details:
                transaction.write({
                    'vipps_user_details': False,
                    'vipps_user_sub': False,
                })
                deleted_count += 1
        
        # Update partner flags
        self.partner_id.update_vipps_data_stats()
        
        _logger.info(
            "Deleted Vipps user data for partner %s (%d transactions) - Reason: %s",
            self.partner_id.name, deleted_count, self.deletion_reason
        )
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Data Deleted'),
                'message': _('Successfully deleted Vipps data from %d transactions') % deleted_count,
                'type': 'success',
            }
        }

    def _create_deletion_audit_log(self, transactions):
        """Create audit log for data deletion"""
        audit_data = {
            'partner_id': self.partner_id.id,
            'partner_name': self.partner_id.name,
            'deletion_date': fields.Datetime.now().isoformat(),
            'deletion_reason': self.deletion_reason,
            'deletion_notes': self.deletion_notes,
            'transactions_affected': len(transactions),
            'transaction_references': transactions.mapped('reference'),
        }
        
        # In a real implementation, this would create a proper audit record
        # For now, just log it
        _logger.info(
            "Vipps data deletion audit log: %s",
            json.dumps(audit_data)
        )


class VippsDataAuditLog(models.Model):
    _name = 'vipps.data.audit.log'
    _description = 'Vipps Data Collection and Processing Audit Log'
    _order = 'create_date desc'

    partner_id = fields.Many2one(
        'res.partner',
        string="Customer",
        required=True,
        index=True
    )
    
    transaction_id = fields.Many2one(
        'payment.transaction',
        string="Transaction",
        index=True
    )
    
    action_type = fields.Selection([
        ('collection', 'Data Collection'),
        ('access', 'Data Access'),
        ('export', 'Data Export'),
        ('deletion', 'Data Deletion'),
        ('consent_given', 'Consent Given'),
        ('consent_withdrawn', 'Consent Withdrawn'),
        ('retention_expired', 'Retention Expired')
    ], string="Action Type", required=True, index=True)
    
    action_date = fields.Datetime(
        string="Action Date",
        default=fields.Datetime.now,
        required=True,
        index=True
    )
    
    user_id = fields.Many2one(
        'res.users',
        string="User",
        default=lambda self: self.env.user,
        required=True
    )
    
    data_types = fields.Char(
        string="Data Types",
        help="Types of data involved in the action"
    )
    
    legal_basis = fields.Selection([
        ('consent', 'Consent'),
        ('contract', 'Contract Performance'),
        ('legal_obligation', 'Legal Obligation'),
        ('vital_interests', 'Vital Interests'),
        ('public_task', 'Public Task'),
        ('legitimate_interests', 'Legitimate Interests')
    ], string="Legal Basis", help="GDPR legal basis for processing")
    
    retention_period = fields.Integer(
        string="Retention Period (Days)",
        help="Data retention period at time of collection"
    )
    
    notes = fields.Text(
        string="Notes",
        help="Additional details about the action"
    )
    
    ip_address = fields.Char(
        string="IP Address",
        help="IP address from which the action was performed"
    )

    @api.model
    def log_data_action(self, partner_id, action_type, **kwargs):
        """Create an audit log entry"""
        vals = {
            'partner_id': partner_id,
            'action_type': action_type,
        }
        vals.update(kwargs)
        
        return self.create(vals)