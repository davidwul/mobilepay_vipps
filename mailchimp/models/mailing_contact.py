import logging

from mailchimp_marketing.api_client import ApiClientError

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)

MAILCHIMP_MEMBER_REQUIRED_FIELDS = [
    "email_address",
    "status",
    "contact_id",
    "email_address",
]


class MailingContact(models.Model):
    _inherit = "mailing.contact"

    mailchimp_contact_id = fields.Char(copy=False, index=True)
    mailchimp_web_id = fields.Char(copy=False)
    mailchimp_last_fetch = fields.Datetime(
        readonly=True, copy=False, default=fields.Datetime.now
    )
    mailchimp_last_export = fields.Datetime(
        readonly=True, copy=False, default=fields.Datetime.now
    )
    mailchimp_url = fields.Char(compute="_compute_mailchimp_url")
    active = fields.Boolean("Active", default=True)
    cleaned = fields.Boolean("Cleaned", default=False, help="Email is invalid.")
    eligible_for_mailchimp_export = fields.Boolean(
        compute="_compute_eligible_for_mailchimp_export"
    )
    eligible_for_mailchimp_fetch = fields.Boolean(
        compute="_compute_eligible_for_mailchimp_fetch"
    )

    _sql_constraints = [
        (
            "mailchimp_contact_id_uniq",
            "unique(mailchimp_contact_id)",
            "MailChimp Contact ID must be unique!",
        )
    ]

    def _compute_mailchimp_url(self):
        for contact in self:
            account = contact.list_ids.mapped("mailchimp_account_id")[:1]
            contact_id = contact.mailchimp_web_id
            if account and contact_id:
                contact.mailchimp_url = (
                    f"https://{account.server_prefix}.admin.mailchimp.com"
                    f"/lists/members/view?id={contact_id}"
                )
            else:
                contact.mailchimp_url = False

    def _compute_eligible_for_mailchimp_export(self):
        """
        Check if the contact is eligible for exporting data to MailChimp.
        It must:
            1. Have an email address
            2. Be subscribed to at least one MailChimp list
            3. Not have a MailChimp Contact ID
               OR Be updated after the last export date
               AND Not have been fetched from MailChimp after the last modification
        @return:
        """
        for contact in self:
            contact.eligible_for_mailchimp_export = (
                contact.email
                and contact.list_ids.filtered("mailchimp_list_id")
                and (
                    not contact.mailchimp_contact_id
                    or contact.write_date > contact.mailchimp_last_export
                    and not contact._was_fetch_last_modification()
                )
            )

    def _compute_eligible_for_mailchimp_fetch(self):
        """
        Check if the contact is eligible for fetching data from MailChimp.
        It must:
            1. Have a MailChimp Contact ID
            2. Be subscribed to at least one MailChimp list
            3. Not have been modified after the last fetch date and last export date
        """
        for contact in self:
            contact.eligible_for_mailchimp_fetch = (
                contact.mailchimp_contact_id
                and contact.list_ids.filtered("mailchimp_list_id")
                and not contact._was_modified_after_last_sync()
            )

    def _was_fetch_last_modification(self):
        """
        Check if the contact was fetched from MailChimp after the last modification.
        @return: True or False
        """
        self.ensure_one()
        difference = abs((self.write_date - self.mailchimp_last_fetch).total_seconds())
        return difference <= 1

    def _was_modified_after_last_sync(self):
        """
        Check if the contact was modified after the last fetch date
        and last export date.
        @return: True or False
        """
        self.ensure_one()
        fetch_diff = (self.write_date - self.mailchimp_last_fetch).total_seconds()
        export_diff = (self.write_date - self.mailchimp_last_export).total_seconds()
        return fetch_diff > 1 and export_diff > 1

    def action_open_mailchimp_backend(self):
        self.ensure_one()
        if self.mailchimp_url:
            return {
                "type": "ir.actions.act_url",
                "url": self.mailchimp_url,
                "target": "new",
            }
        return True

    @api.model
    def mailchimp_import(self, mailchimp_data):
        """
        Create or update a mailing contact with the mailchimp_data.
        @param mailchimp_data: Member Data given by MailChimp API.
        @return: mailing.contact record
        """
        contact = self.with_context(active_test=False).search(
            [("mailchimp_contact_id", "=", mailchimp_data.get("contact_id"))]
        )
        vals = contact._prepare_mailchimp_data(mailchimp_data)
        if contact:
            contact.write(vals)
        else:
            contact = self.create(vals)
        return contact.exists()

    def mailchimp_fetch(self):
        """Update the contact with the data from MailChimp."""
        for contact in self.filtered("eligible_for_mailchimp_fetch"):
            for mailing_list in self.list_ids.filtered("mailchimp_list_id"):
                try:
                    client = mailing_list.mailchimp_account_id._get_mailchimp_client()
                    response = client.lists.get_list_member(
                        mailing_list.mailchimp_list_id,
                        contact.mailchimp_contact_id,
                    )
                    contact.write(contact._prepare_mailchimp_data(response))
                    if mailing_list.mailchimp_import_tags:
                        contact._import_tags()
                except ApiClientError as error:
                    _logger.error(error.text)
        return True

    def mailchimp_export(self):
        _logger.info("Exporting %s contacts to MailChimp", len(self))
        for contact in self.filtered("eligible_for_mailchimp_export"):
            for subscription in contact.subscription_ids.filtered(
                "list_id.mailchimp_list_id"
            ):
                mailing_list = subscription.list_id
                status = "subscribed" if not subscription.opt_out else "unsubscribed"
                try:
                    with self.env.cr.savepoint():
                        client = (
                            mailing_list.mailchimp_account_id._get_mailchimp_client()
                        )
                        contact_id = contact.mailchimp_contact_id
                        if not contact_id:
                            try:
                                contact_data = client.lists.get_list_member(
                                    mailing_list.mailchimp_list_id,
                                    contact.email_normalized,
                                )
                                contact_id = contact_data.get("contact_id")
                                status = contact_data.get("status")
                                _logger.info(
                                    "Existing contact %s found in MailChimp with id %s",
                                    contact.email,
                                    contact_id,
                                )
                            except ApiClientError:
                                _logger.info("No existing contact found in MailChimp.")
                        operation = (
                            client.lists.update_list_member
                            if contact_id
                            else client.lists.set_list_member
                        )
                        response = operation(
                            mailing_list.mailchimp_list_id,
                            contact_id,
                            {
                                "skip_merge_validation": True,
                                "email_address": contact.email,
                                "status": status,
                                "status_if_new": status,
                                "merge_fields": contact._get_merged_fields(),
                            },
                        )
                        contact_data = contact._prepare_mailchimp_data(response)
                        contact_data["mailchimp_last_export"] = fields.Datetime.now()
                        contact.write(contact_data)
                        _logger.info(
                            "Contact %s exported to MailChimp list %s with id %s",
                            contact.email,
                            mailing_list.name,
                            response.get("contact_id"),
                        )
                        if mailing_list.mailchimp_export_tags:
                            contact._export_tags()
                        if not contact.active:
                            # Archive contact in MailChimp
                            client.lists.delete_list_member(
                                mailing_list.mailchimp_list_id,
                                contact.mailchimp_contact_id,
                            )
                except ApiClientError as error:
                    _logger.error(error.text)
        return True

    def _prepare_mailchimp_data(self, mailchimp_data):
        """
        Convert the mailchimp_data to a dictionary of values to write on the
        contact.
        @param mailchimp_data: Member Data given by MailChimp API.
        @return: Odoo compatible dictionary of values.
        """
        if not isinstance(mailchimp_data, dict) or not any(
            [p in mailchimp_data for p in MAILCHIMP_MEMBER_REQUIRED_FIELDS]
        ):
            raise ValidationError(_("Invalid MailChimp data!"))
        list_id = mailchimp_data.get("list_id")
        mailing_list = self.env["mailing.list"].search(
            [("mailchimp_list_id", "=", list_id)]
        )
        subscription = self.env["mailing.subscription"].search(
            [
                ("contact_id", "=", self.id),
                ("list_id", "=", mailing_list.id),
            ]
        )
        status = mailchimp_data.get("status")
        subscription_vals = {
            "list_id": mailing_list.id,
            "opt_out": status in ("unsubscribed", "cleaned", "archived"),
        }
        vals = {
            "mailchimp_contact_id": mailchimp_data.get("contact_id"),
            "mailchimp_web_id": mailchimp_data.get("web_id"),
            "name": mailchimp_data.get("full_name"),
            "email": mailchimp_data.get("email_address"),
            "subscription_ids": [(1, subscription.id, subscription_vals)]
            if subscription
            else [(0, 0, subscription_vals)],
            "active": status != "archived",
            "cleaned": status == "cleaned",
            "mailchimp_last_fetch": fields.Datetime.now(),
        }
        return vals

    def _get_merged_fields(self):
        """
        Get the merge fields to push to MailChimp.
        @return: dictionary of merge fields.
        """
        self.ensure_one()
        return {
            merge_field.tag: safe_eval(merge_field.value, {"contact": self})
            for merge_field in self.list_ids.mapped("mailchimp_merge_field_ids")
            if merge_field.value
        }

    def _export_tags(self):
        self.ensure_one()
        for mailing_list in self.list_ids.filtered("mailchimp_account_id"):
            try:
                client = mailing_list.mailchimp_account_id._get_mailchimp_client()
                response = client.lists.get_list_member_tags(
                    mailing_list.mailchimp_list_id, self.mailchimp_contact_id
                )
                mailchimp_tags = response.get("tags", [])
                odoo_tags = self.mapped("tag_ids").with_context(lang="en_US")
                del_command = [
                    {"name": tag.get("name"), "status": "inactive"}
                    for tag in mailchimp_tags
                    if tag.get("id") not in odoo_tags.mapped("mailchimp_id")
                ]
                add_command = [
                    {"name": tag.name, "status": "active"} for tag in odoo_tags
                ]
                client.lists.update_list_member_tags(
                    mailing_list.mailchimp_list_id,
                    self.mailchimp_contact_id,
                    {"tags": del_command + add_command},
                )
            except ApiClientError as e:
                _logger.error(
                    "Couldn't sync tags for contact %s: %s", self.email, e.text
                )

    def _import_tags(self):
        self.ensure_one()
        for mailing_list in self.list_ids.filtered("mailchimp_account_id"):
            try:
                client = mailing_list.mailchimp_account_id._get_mailchimp_client()
                response = client.lists.get_list_member_tags(
                    mailing_list.mailchimp_list_id, self.mailchimp_contact_id
                )
                self.tag_ids = False
                for tag in response.get("tags", []):
                    self.tag_ids |= (
                        self.env["res.partner.category"]
                        .with_context(lang="en_US")
                        .search_or_create_mailchimp_tag(tag)
                    )
            except ApiClientError as e:
                _logger.error(
                    "Couldn't sync tags for contact %s: %s", self.email, e.text
                )

    def unlink(self):
        for contact in self:
            if contact.mailchimp_contact_id:
                for mailing_list in contact.list_ids.filtered("mailchimp_account_id"):
                    try:
                        client = (
                            mailing_list.mailchimp_account_id._get_mailchimp_client()
                        )
                        client.lists.delete_list_member(
                            mailing_list.mailchimp_list_id, contact.mailchimp_contact_id
                        )
                    except ApiClientError as e:
                        _logger.error(
                            "Couldn't delete contact %s from MailChimp: %s",
                            contact.email,
                            e.text,
                        )
        return super().unlink()
