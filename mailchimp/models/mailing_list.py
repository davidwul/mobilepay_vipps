import logging

from mailchimp_marketing.api_client import ApiClientError

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

MAX_MEMBERS_FETCH = 1000

_logger = logging.getLogger(__name__)


class MassMailingList(models.Model):
    _inherit = "mailing.list"

    mailchimp_list_id = fields.Char("Mailchimp List ID", copy=False)
    mailchimp_web_id = fields.Integer("Mailchimp Web ID", copy=False)
    mailchimp_account_id = fields.Many2one(
        "mailchimp.account", "MailChimp Account", copy=False
    )
    mailchimp_last_fetch = fields.Datetime(readonly=True, copy=False)
    mailchimp_auto_export_member = fields.Boolean(
        "Auto Export Member?", copy=False, default=True
    )
    mailchimp_merge_field_ids = fields.One2many(
        "mailchimp.merge.field", "list_id", string="Merge Fields"
    )
    mailchimp_export_tags = fields.Boolean("Export Tags?", default=True)
    mailchimp_import_tags = fields.Boolean(
        "Import Tags?",
    )

    _sql_constraints = [
        (
            "mailchimp_list_id_uniq",
            "unique(mailchimp_list_id)",
            "MailChimp List ID must be unique!",
        )
    ]

    @api.constrains("mailchimp_export_tags", "mailchimp_import_tags")
    def _check_tags_settings(self):
        for record in self:
            if record.mailchimp_export_tags and record.mailchimp_import_tags:
                raise ValidationError(
                    _("You cannot import and export tags. The sync is unidirectional.")
                )

    @api.onchange("mailchimp_export_tags", "mailchimp_import_tags")
    def _onchange_tags_settings(self):
        if self.mailchimp_export_tags:
            self.mailchimp_import_tags = False
        elif self.mailchimp_import_tags:
            self.mailchimp_export_tags = False

    @api.model
    def mailchimp_update_list_info(self, mailchimp_data):
        """
        Find the mailing list associated with the mailchimp_data and
        update the mailing list. Create a new one if not found.
        @param mailchimp_data: Data given by MailChimp API
        @return: the mailing list updated or created.
        """
        result = self
        mailchimp_id = mailchimp_data.get("id")
        if mailchimp_id:
            result = self.search([("mailchimp_list_id", "=", mailchimp_id)])
            if result:
                result.write(self._prepare_mailchimp_data(mailchimp_data))
            else:
                result = self.create(self._prepare_mailchimp_data(mailchimp_data))
        return result

    def mailchimp_fetch_members(self, offset=0):
        """
        Sync mailing contacts with Mailchimp audience members.
        @return: mailing.contact records updated or created.
        """
        mailing_contacts = self.env["mailing.contact"]
        for mailing_list in self:
            try:
                since_date = (
                    mailing_list.mailchimp_last_fetch
                    and mailing_list.mailchimp_last_fetch.isoformat()
                )
                client = mailing_list.mailchimp_account_id._get_mailchimp_client()
                response = client.lists.get_list_members_info(
                    mailing_list.mailchimp_list_id,
                    since_last_changed=since_date or None,
                    count=MAX_MEMBERS_FETCH,
                    offset=offset,
                )
            except ApiClientError as error:
                _logger.error(error.text)
                continue
            members = response.get("members", [])
            for member in members:
                mailing_contacts |= mailing_contacts.mailchimp_import(member)
            total = response.get("total_items", 0)
            if total > MAX_MEMBERS_FETCH + offset:
                mailing_list.mailchimp_fetch_members(offset + MAX_MEMBERS_FETCH)
        return mailing_contacts

    def mailchimp_export_members(self):
        lastcall = self.env.ref("mailchimp.export_members").lastcall
        contacts = self.env["mailing.contact"].search(
            [
                ("list_ids.id", "in", self.ids),
                "|",
                ("mailchimp_contact_id", "=", False),
                ("mailchimp_last_export", "<", lastcall),
            ]
        )
        contacts.delayable().mailchimp_export().set(
            priority=50).split(100, chain=True).delay()

    def mailchimp_update_merge_fields(self):
        self.ensure_one()
        try:
            client = self.mailchimp_account_id._get_mailchimp_client()
            response = client.lists.get_list_merge_fields(
                self.mailchimp_list_id, count=80
            )
            merge_field_ids = []
            for merge_field_data in response.get("merge_fields", []):
                merge_id = merge_field_data.get("merge_id")
                merge_field_ids.append(merge_id)
                merge_field_vals = {
                    "list_id": self.id,
                    "merge_id": merge_id,
                    "tag": merge_field_data.get("tag"),
                    "name": merge_field_data.get("name"),
                    "type": merge_field_data.get("type"),
                    "required": merge_field_data.get("required"),
                    "default_value": merge_field_data.get("default_value"),
                    "public": merge_field_data.get("public"),
                    "display_order": merge_field_data.get("display_order"),
                }
                options = merge_field_data.get("options", {})
                if options:
                    merge_field_vals["date_format"] = options.get("date_format")
                merge_field = (
                    self.env["mailchimp.merge.field"]
                    .with_context(skip_mailchimp_sync=True)
                    .search(
                        [
                            ("list_id", "=", self.id),
                            ("merge_id", "=", merge_id),
                        ]
                    )
                )
                if merge_field:
                    merge_field.write(merge_field_vals)
                else:
                    merge_field.create(merge_field_vals)
            # Delete merge fields that are not in Mailchimp anymore
            self.mailchimp_merge_field_ids.filtered(
                lambda m: m.merge_id not in merge_field_ids
            ).unlink()
        except ApiClientError as error:
            raise UserError(error.text) from error

    @api.model
    def _prepare_mailchimp_data(self, mailchimp_data):
        """
        Prepare the data to update or create a mailing list
        @param mailchimp_data: Data given by MailChimp API
        @return: the data to write or create
        """
        return {
            "mailchimp_list_id": mailchimp_data.get("id"),
            "mailchimp_web_id": mailchimp_data.get("web_id"),
            "mailchimp_account_id": mailchimp_data.get("account_id"),
            "name": mailchimp_data.get("name"),
        }
