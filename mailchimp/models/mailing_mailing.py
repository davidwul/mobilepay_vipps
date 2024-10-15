import logging

from mailchimp_marketing.api_client import ApiClientError
from requests import get

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..tools.date_convert import mailchimp_date_to_datetime

_logger = logging.getLogger(__name__)

MAILCHIMP_STATUS_MAPPING = {
    "sent": "done",
    "sending": "sending",
    "paused": "in_queue",
    "schedule": "in_queue",
    "save": "draft",
    "canceled": "cancel",
    "canceling": "cancel",
}
MAX_STATS_FETCH = 1000


class MassMailing(models.Model):
    _inherit = "mailing.mailing"

    mailchimp_account_id = fields.Many2one(
        "mailchimp.account",
        string="MailChimp Account",
    )
    mailchimp_id = fields.Char("MailChimp ID", copy=False, readonly=True)
    mailchimp_web_id = fields.Integer("MailChimp Web ID", copy=False, readonly=True)
    mailchimp_url = fields.Char(compute="_compute_mailchimp_url")
    last_report_import_date = fields.Datetime("Last stats fetched", copy=False)
    mailchimp_archive_url = fields.Char(readonly=True)
    mailchimp_template_id = fields.Many2one(
        "mailchimp.template",
        string="MailChimp Template",
    )
    mailchimp_recipients = fields.Html(
        help="Recipients selection description from MailChimp",
        readonly=True,
    )
    mailchimp_recipients_count = fields.Integer(readonly=True)
    state = fields.Selection(
        selection_add=[("cancel", "Cancelled")], ondelete={"cancel": "set default"}
    )

    _sql_constraints = [
        (
            "mailchimp_id_uniq",
            "unique(mailchimp_id)",
            "MailChimp ID must be unique!",
        )
    ]

    def _compute_mailchimp_url(self):
        for record in self:
            if record.mailchimp_web_id:
                account = record.mailchimp_account_id
                record.mailchimp_url = f"https://{account.server_prefix}.admin.mailchimp.com/campaigns/show/?id={record.mailchimp_web_id}"
            else:
                record.mailchimp_url = ""

    def _compute_total(self):
        # Include MailChimp stats in total
        super()._compute_total()
        for mailing in self.filtered("mailchimp_id"):
            mailing.total = mailing.mailchimp_recipients_count

    def write(self, values):
        """
        Prevent writing on MailChimp mailings.
        @param values: values to write
        @return: Warning in case of write on MailChimp mailing
        """
        fetch_date = len(values) == 1 and "last_report_import_date" in values
        if (
            self.filtered("mailchimp_id")
            and not self.env.context.get("mailchimp_update")
            and not fetch_date
        ):
            self.env.user.notify_danger(
                _(
                    "Some changes may not be taken into account on MailChimp mailings. "
                    "Please modify it from MailChimp."
                )
            )
        return super().write(values)

    def action_open_mailchimp_backend(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": self.mailchimp_url,
            "target": "new",
        }

    def multi_refresh_mailchimp(self):
        """
        Refresh MailChimp stats for multiple mailings
        :return: True
        """
        for mailing in self:
            mailing.with_delay(channel="root.mailchimp").action_refresh_mailchimp()
        self.env.user.notify_success(
            _("MailChimp info is being refreshed in background.")
        )
        return True

    def action_refresh_mailchimp(self, offset=0, skip_basic_info=False):
        """
        Refresh Campaign Data from MailChimp
        @param offset: pagination offset for fetching stats data
        @param skip_basic_info: avoid fetching basic campaign info
        @return:
        """
        self.ensure_one()
        self = self.with_context(mailchimp_update=True)
        try:
            client = self.mailchimp_account_id._get_mailchimp_client()
            if not skip_basic_info:
                response = client.campaigns.get(self.mailchimp_id)
                self.mailchimp_update_campaign_info(
                    response, self.mailchimp_account_id.id
                )
            if self.state != "done":
                # There is no need to fetch stats for campaigns that are not sent
                return True
            params = {"count": MAX_STATS_FETCH, "offset": offset}
            if self.last_report_import_date:
                params["since"] = self.last_report_import_date.isoformat()
            response = client.reports.get_email_activity_for_campaign(
                self.mailchimp_id, **params
            )
            self._update_mailchimp_report(response)
            total = response.get("total_items", 0)
            if total > offset + MAX_STATS_FETCH:
                self.action_refresh_mailchimp(
                    offset + MAX_STATS_FETCH, skip_basic_info=True
                )
            else:
                self.last_report_import_date = fields.Datetime.now()
            return True
        except ApiClientError as error:
            raise UserError(error.text) from error

    def action_send_mail(self, res_ids=None):
        """
        Send Mail through MailChimp
        :param res_ids: record IDs
        :return: True
        """
        mailchimp_mailings = self.filtered("mailchimp_id").with_context(
            mailchimp_update=True
        )
        regular_mailings = self - mailchimp_mailings
        for mailing in mailchimp_mailings:
            try:
                client = mailing.mailchimp_account_id._get_mailchimp_client()
                response = client.campaigns.send(mailing.mailchimp_id)
                if response.get("status", "204") != "204":
                    raise UserError(response.get("detail"))
                mailing.write(
                    {
                        "state": "done",
                        "sent_date": fields.Datetime.now(),
                        # send the KPI mail only if it's the first sending
                        "kpi_mail_required": not mailing.sent_date,
                    }
                )
            except ApiClientError as error:
                raise UserError(error.text) from error
        if regular_mailings:
            super(MassMailing, regular_mailings).action_send_mail(res_ids)
        return True

    def action_schedule(self):
        # This will allow the operation to update the state of the mailing
        return super(
            MassMailing, self.with_context(mailchimp_update=True)
        ).action_schedule()

    def action_put_in_queue(self):
        # This will allow the operation to update the state of the mailing
        return super(
            MassMailing, self.with_context(mailchimp_update=True)
        ).action_put_in_queue()

    def action_cancel(self):
        # This will allow the operation to update the state of the mailing
        return super(
            MassMailing, self.with_context(mailchimp_update=True)
        ).action_cancel()

    def unlink(self):
        for mailing in self.filtered("mailchimp_id"):
            try:
                client = mailing.mailchimp_account_id._get_mailchimp_client()
                client.campaigns.remove(mailing.mailchimp_id)
            except ApiClientError as error:
                _logger.error(error.text)
        super().unlink()

    @api.model
    def mailchimp_update_campaign_info(self, mailchimp_data, account_id):
        """
        Update Campaign Info
        :param mailchimp_data: Campaign Data from MailChimp
        :param account_id: MailChimp Account record ID
        :return: The updated mailing record
        """
        if not mailchimp_data or not isinstance(mailchimp_data, dict):
            return True
        mailchimp_id = mailchimp_data.get("id")
        mailchimp_data = self._prepare_mailchimp_data(mailchimp_data, account_id)
        mailing = self.with_context(mailchimp_update=True).search(
            [("mailchimp_id", "=", mailchimp_id)]
        )
        if not mailing:
            mailing = self.create(mailchimp_data)
        else:
            mailing.write(mailchimp_data)
        return mailing

    def _prepare_mailchimp_data(self, mailchimp_data, account_id):
        """
        Prepare MailChimp Data for Odoo write or create
        :param mailchimp_data: Data from MailChimp
        :param account_id: MailChimp Account record ID
        :return: Prepared Data (odoo vals)
        """
        if not mailchimp_data or not isinstance(mailchimp_data, dict):
            return {}
        campaign_settings = mailchimp_data.get("settings", {})
        recipients = mailchimp_data.get("recipients", {})
        template = self.env["mailchimp.template"].fetch_or_create(
            self.mailchimp_account_id, campaign_settings.get("template_id")
        )
        mailchimp_status = mailchimp_data.get("status")
        active = mailchimp_status != "archived"
        res = {
            "mailchimp_id": mailchimp_data.get("id"),
            "mailchimp_web_id": mailchimp_data.get("web_id"),
            "preview": campaign_settings.get("preview_text"),
            "mailchimp_template_id": template.id,
            "mailchimp_archive_url": mailchimp_data.get("archive_url"),
            "mailchimp_recipients": recipients.get("segment_text"),
            "mailchimp_recipients_count": recipients.get("recipient_count"),
            "subject": campaign_settings.get("subject_line", "NO SUBJECT"),
            "name": campaign_settings.get("title"),
            "email_from": campaign_settings.get("from_name", self.env.user.email),
            "reply_to": campaign_settings.get("reply_to", self.env.user.email),
            "active": active,
            "mailchimp_account_id": account_id,
            "body_html": get(mailchimp_data.get("long_archive_url")).text,
            "mailing_type": "mail",
        }
        if active:
            res["state"] = MAILCHIMP_STATUS_MAPPING.get(mailchimp_status)
        send_time = mailchimp_data.get("send_time")
        if send_time:
            res["sent_date"] = mailchimp_date_to_datetime(send_time)
        list_id = mailchimp_data.get("recipients", {}).get("list_id")
        if list_id:
            contact_list = self.env["mailing.list"].search(
                [("mailchimp_list_id", "=", list_id)]
            )
            res["contact_list_ids"] = [(6, 0, contact_list.ids)]
        return res

    def _update_mailchimp_report(self, report_data):
        """
        Update Campaign Statistics with report from MailChimp
        :param report_data: Report Data from MailChimp
        :return: True
        """
        if not report_data or not isinstance(report_data, dict):
            return True
        report_data = report_data.get("emails", [])
        for email_activity in report_data:
            self.env["mailing.trace"].mailchimp_update_trace(email_activity, self)
        return True

    @api.model
    def _process_mass_mailing_queue(self):
        self = self.with_context(mailchimp_update=True)
        mailchimp_mailings = self.search(
            [
                ("mailchimp_id", "!=", False),
                ("state", "=", "in_queue"),
                "|",
                ("schedule_date", "<", fields.Datetime.now()),
                ("schedule_date", "=", False),
            ]
        )
        for mass_mailing in mailchimp_mailings:
            mass_mailing.state = "sending"
            mass_mailing.action_send_mail()
        return super()._process_mass_mailing_queue()
