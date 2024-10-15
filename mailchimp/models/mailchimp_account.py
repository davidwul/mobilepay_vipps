import logging

import mailchimp_marketing
from mailchimp_marketing.api_client import ApiClientError

from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools import ormcache

from ..tools.date_convert import mailchimp_date_to_datetime

MAX_CAMPAIGN_FETCH = 1000

_logger = logging.getLogger(__name__)


class MailChimpAccounts(models.Model):
    _name = "mailchimp.account"
    _description = "Mailchimp Accounts"

    name = fields.Char(
        "Name", required=True, copy=False, help="Name of your MailChimp account"
    )

    # Authentication
    server_prefix = fields.Char("Server Prefix", required=True, copy=False)
    api_key = fields.Char("API Key", required=True, copy=False)
    list_ids = fields.One2many(
        "mailing.list", "mailchimp_account_id", string="Lists/Audience", copy=False
    )
    campaign_ids = fields.One2many(
        "mailing.mailing", "mailchimp_account_id", string="Campaigns", copy=False
    )
    last_campaign_fetch = fields.Datetime("Fetch Since")

    _sql_constraints = [
        (
            "api_keys_uniq",
            "unique(api_key)",
            "API keys must be unique per MailChimp Account!",
        ),
    ]

    def get_mailchimp_scheduled_actions(self):
        action = self.env.ref("base.ir_cron_act").read()[0]
        action["domain"] = [("name", "ilike", "MailChimp:")]
        return action

    def refresh_lists(self):
        for account in self:
            try:
                client = account._get_mailchimp_client()
                response = client.lists.get_all_lists(count=1000)
                for mailing_list_data in response.get("lists", []):
                    mailing_list_data["account_id"] = account.id
                    self.env["mailing.list"].mailchimp_update_list_info(
                        mailing_list_data
                    )
            except ApiClientError as error:
                raise UserError(f"Error: {error.text}") from error
        return True

    def test_connection(self):
        self.ensure_one()
        try:
            client = self._get_mailchimp_client()
            response = client.ping.get()
        except ApiClientError as error:
            raise UserError(f"Error: {error.text}") from error
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("MailChimp connection successful!"),
                "message": response.get("health_status", _("API Key is valid!")),
                "type": "success",
            },
        }

    def fetch_campaigns(self):
        """
        Retrieve new campaigns from Mailchimp and update all campaigns not yet sent.
        """
        self.ensure_one()
        mailings = self.env["mailing.mailing"]
        try:
            client = self._get_mailchimp_client()
            params = {
                "count": MAX_CAMPAIGN_FETCH,
                "sort_field": "create_time",
                "sort_dir": "ASC",
            }
            if self.last_campaign_fetch:
                params["since_create_time"] = self.last_campaign_fetch.isoformat()
            response = client.campaigns.list(**params)
            for campaign in response.get("campaigns", []):
                mailings |= mailings.mailchimp_update_campaign_info(campaign, self.id)
                campaign_date = mailchimp_date_to_datetime(campaign.get("create_time"))
                if campaign_date > self.last_campaign_fetch:
                    self.last_campaign_fetch = campaign_date
                # pylint: disable=E8102
                self.env.cr.commit()
        except ApiClientError as error:
            _logger.error("Error fetching campaigns: %s", error.text)
        pending = mailings.search(
            [("mailchimp_id", "!=", False), ("state", "not in", ["done", "cancel"])]
        )
        pending.multi_refresh_mailchimp()
        mailings |= pending
        return mailings

    @ormcache("self.api_key", "self.server_prefix")
    def _get_mailchimp_client(self):
        client = mailchimp_marketing.Client()
        client.set_config({"api_key": self.api_key, "server": self.server_prefix})
        return client
