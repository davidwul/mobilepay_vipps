from mailchimp_marketing.api_client import ApiClientError

from odoo import fields, models


class MailChimpMergeField(models.Model):
    _name = "mailchimp.merge.field"
    _description = "Mailchimp Merge Field"
    _order = "display_order,list_id,name"

    name = fields.Char(
        "Name",
        required=True,
        copy=False,
    )
    merge_id = fields.Integer("Merge ID", copy=False)
    tag = fields.Char(
        "Merge Field Tag",
        help="The tag used in Mailchimp campaigns and for the /members endpoint.",
    )
    type = fields.Selection(
        [
            ("text", "Text"),
            ("number", "Number"),
            ("address", "Address"),
            ("phone", "Phone"),
            ("date", "Date"),
            ("radio", "Radio"),
            ("dropdown", "Dropdown"),
            ("birthday", "Birthday"),
            ("zip", "Zip"),
            ("imageurl", "ImageURL"),
            ("url", "URL"),
        ],
    )
    date_format = fields.Char("Date Format")
    required = fields.Boolean(
        "Required?", copy=False, help="Merge field is required or not."
    )
    public = fields.Boolean(
        "Visible?",
        copy=False,
        help="Whether the merge field is displayed on the signup form.",
    )
    default_value = fields.Char(
        "Default Value", help="The default value for the merge field if null."
    )
    display_order = fields.Integer(
        "Display Order",
        help="The order that the merge field displays on the list signup form.",
    )
    list_id = fields.Many2one(
        "mailing.list",
        string="Associated MailChimp List",
        ondelete="cascade",
        required=True,
        copy=False,
    )
    value = fields.Char(
        string="Field Value",
        help="Write python code to extract value. Use 'contact' variable to retrieve "
        "the value of the field from the mailing.contact record.",
    )

    _sql_constraints = [
        (
            "merge_id_list_id_uniq",
            "unique(merge_id, list_id)",
            "Merge ID must be unique per MailChimp Lists!",
        ),
    ]

    def write(self, vals):
        # Push changes to Mailchimp
        res = super().write(vals)
        if not self.env.context.get("skip_mailchimp_sync"):
            for merge_field in self:
                try:
                    client = (
                        merge_field.list_id.mailchimp_account_id._get_mailchimp_client()
                    )
                    client.lists.update_list_merge_field(
                        merge_field.list_id.mailchimp_list_id,
                        merge_field.merge_id,
                        merge_field._prepare_mailchimp_data(),
                    )
                except ApiClientError as e:
                    raise e
        return res

    def _prepare_mailchimp_data(self):
        self.ensure_one()
        return {
            "name": self.name,
            "tag": self.tag,
            "type": self.type,
            "date_format": self.date_format,
            "required": self.required,
            "public": self.public,
            "default_value": self.default_value,
            "display_order": self.display_order,
        }
