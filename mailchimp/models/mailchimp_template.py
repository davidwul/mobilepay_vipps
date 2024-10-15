import logging
from datetime import timedelta

from mailchimp_marketing.api_client import ApiClientError

from odoo import api, fields, models

from ..tools.date_convert import mailchimp_date_to_datetime

_logger = logging.getLogger(__name__)

REFRESH_RATE = 60 * 60  # Refresh template every hour


class MailChimpTemplates(models.Model):
    _name = "mailchimp.template"
    _description = "MailChimp Template"

    name = fields.Char(
        "Name",
        required=True,
        help="The name of the template.",
    )
    account_id = fields.Many2one(
        "mailchimp.account", string="Account", required=True, ondelete="cascade"
    )
    template_id = fields.Integer("Template ID", copy=False, required=True, index=True)
    type = fields.Selection(
        [("user", "User"), ("gallery", "Gallery"), ("base", "Base")],
        default="user",
        copy=False,
        help="The type of template (user, base, or gallery).",
    )
    category = fields.Char(
        "Template Category",
        help="If available, the category the template is listed in.",
    )
    date_edited = fields.Datetime("Edited On")
    created_by = fields.Char()
    edited_by = fields.Char()
    last_fetch = fields.Datetime("Last Fetched On")
    active = fields.Boolean("Active", default=True)
    thumbnail = fields.Char()
    url = fields.Char()

    _sql_constraints = [
        ("template_id_uniq", "unique(template_id)", "Template ID must be unique!"),
    ]

    def action_open_mailchimp_backend(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": self.url,
            "target": "new",
        }

    @api.model
    def fetch_all(self, mailchimp_account, offset=0):
        """
        Fetch all templates from MailChimp
        :param mailchimp_account: MailChimp Account record
        :param offset: Offset
        :return: Template Records
        """
        templates = self
        try:
            client = mailchimp_account._get_mailchimp_client()
            response = client.templates.list(count=1000, offset=offset)
            for template in response.get("templates", []):
                template_id = template.get("id")
                if template_id:
                    template = self.fetch_or_create(template_id)
                    templates |= template
        except ApiClientError as error:
            _logger.error(error.text)
        return templates

    @api.model
    def fetch_or_create(self, mailchimp_account, template_id):
        """
        Fetch or Create Template
        :param mailchimp_account: MailChimp Account record
        :param template_id: Template ID
        :return: Template Record
        """
        template = self.with_context(active_test=False).search(
            [("template_id", "=", template_id)]
        )
        if not template or template.last_fetch < fields.Datetime.now() - timedelta(
            seconds=REFRESH_RATE
        ):
            template = template._fetch(mailchimp_account, template_id)
        return template

    def _fetch(self, mailchimp_account, template_id):
        """
        Fetch Template from MailChimp
        :param mailchimp_account: MailChimp Account record
        :param template_id: Template ID
        :return: Template Record
        """
        template = self
        try:
            client = mailchimp_account._get_mailchimp_client()
            response = client.templates.get_template(str(template_id))
            template_vals = self._prepare_template_data(response, mailchimp_account.id)
            if template:
                template.write(template_vals)
            else:
                template = self.create(template_vals)
        except ApiClientError as error:
            _logger.error(error.text)
        return template

    @api.model
    def _prepare_template_data(self, mailchimp_data, account_id):
        """
        Prepare MailChimp Data for Odoo write or create
        :param mailchimp_data: Data from MailChimp
        :param account_id: MailChimp Account record ID
        :return: Prepared Data (odoo vals)
        """
        if not mailchimp_data or not isinstance(mailchimp_data, dict):
            return {}
        return {
            "name": mailchimp_data.get("name"),
            "account_id": account_id,
            "template_id": mailchimp_data.get("id"),
            "type": mailchimp_data.get("type"),
            "category": mailchimp_data.get("category"),
            "create_date": mailchimp_date_to_datetime(
                mailchimp_data.get("date_created")
            ),
            "date_edited": mailchimp_date_to_datetime(
                mailchimp_data.get("date_edited")
            ),
            "created_by": mailchimp_data.get("created_by"),
            "edited_by": mailchimp_data.get("edited_by"),
            "last_fetch": fields.Datetime.now(),
            "active": mailchimp_data.get("active"),
            "thumbnail": mailchimp_data.get("thumbnail"),
            "url": mailchimp_data.get("_links", [{}])[0].get("href"),
        }
