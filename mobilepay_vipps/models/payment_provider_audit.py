
from odoo import models, fields

class PaymentProviderAudit(models.Model):
    _name = 'payment.provider.audit'
    _description = 'Audit log for payment provider'

    provider_id = fields.Many2one('payment.provider', string='Provider')
    action = fields.Char(string='Action')
    timestamp = fields.Datetime(string='Timestamp', default=fields.Datetime.now)
    user_id = fields.Many2one('res.users', string='User')
