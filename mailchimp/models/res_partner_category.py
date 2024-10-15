from odoo import api, fields, models


class ResPartnerCategory(models.Model):
    _inherit = "res.partner.category"

    mailchimp_id = fields.Char("Mailchimp Id", copy=False, readonly=True, index=True)

    _sql_constraints = [
        ("mailchimp_id_uniq", "unique(mailchimp_id)", "MailChimp ID must be unique!")
    ]

    @api.model
    def search_or_create_mailchimp_tag(self, mailchimp_data):
        """
        Search or create a tag given by MailChimp API
        @param mailchimp_data: dict of data given by MailChimp API
        @return: res.partner.category record
        """
        mailchimp_id = mailchimp_data.get("id")
        mailchimp_name = mailchimp_data.get("name")
        result = self.search([("mailchimp_id", "=", mailchimp_id)])
        if not result:
            result = self.search([("name", "=", mailchimp_name)], limit=1)
            if result:
                result.mailchimp_id = mailchimp_id
            else:
                result = self.create(
                    {"name": mailchimp_name, "mailchimp_id": mailchimp_id}
                )
        return result
