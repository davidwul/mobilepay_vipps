from mailchimp_marketing.api_client import ApiClientError

from odoo import models
from odoo.exceptions import UserError
from odoo.tools.mail import email_normalize_all


class TestMassMailing(models.TransientModel):
    _inherit = "mailing.mailing.test"

    def send_mail_test(self):
        self.ensure_one()
        if self.mass_mailing_id.mailchimp_id:
            try:
                client = (
                    self.mass_mailing_id.mailchimp_account_id._get_mailchimp_client()
                )
                client.campaigns.send_test_email(
                    self.mass_mailing_id.mailchimp_id,
                    {
                        "test_emails": email_normalize_all(self.email_to),
                        "send_type": "html",
                    },
                )
                return True
            except ApiClientError as error:
                raise UserError(error.text) from error
        return super().send_mail_test()
