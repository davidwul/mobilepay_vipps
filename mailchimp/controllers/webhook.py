import logging
from enum import Enum

from werkzeug.exceptions import NotFound

from odoo import fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)


class RequestType(Enum):
    # This webhook is not designed for campaign status updates,
    # only for contact updates
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    PROFILE = "profile"
    CLEANED = "cleaned"


class MailChimp(http.Controller):
    @http.route("/mailchimp/webhook/", type="json", auth="public", csrf=False)
    def mailchimp_api(self, **kwargs):
        contact_obj = request.env["mailing.contact"].sudo()
        mailing_list_obj = request.env["mailing.list"].sudo()
        mailchimp_accounts = request.env["mailchimp.account"].sudo().search([])
        _logger.debug("Mailchimp Webhook called: %s", str(kwargs))
        request_type = kwargs.get("type", False)
        request_data = kwargs.get("data", {})
        list_id = request_data.get("list_id", False)
        mailchimp_id = request_data.get("id", False)
        mailing_list = mailing_list_obj.search([("mailchimp_list_id", "=", list_id)])
        if not mailing_list:
            mailchimp_accounts.refresh_lists()
            mailing_list = mailing_list_obj.search(
                [("mailchimp_list_id", "=", list_id)]
            )
        contact = contact_obj.search([("mailchimp_contact_id", "=", mailchimp_id)])
        if request_type == RequestType.SUBSCRIBE.value:
            if not mailing_list:
                raise NotFound("Mailing list not found")
            if contact:
                contact.write(
                    {
                        "list_ids": [(4, mailing_list.id)],
                        "mailchimp_last_fetch": fields.Datetime.now(),
                    }
                )
            else:
                contact = contact_obj.create(
                    {
                        "mailchimp_contact_id": mailchimp_id,
                        "list_ids": [(4, mailing_list.id)],
                    }
                )
            contact.mailchimp_fetch()
        elif request_type == RequestType.UNSUBSCRIBE.value:
            if contact and mailing_list:
                subscription = contact.subscription_list_ids.filtered(
                    lambda sub: sub.list_id.id == mailing_list.id
                )
                subscription.opt_out = True
        elif request_type == RequestType.PROFILE.value:
            if contact:
                contact.mailchimp_fetch()
        elif request_type == RequestType.CLEANED.value:
            if contact:
                contact.write(
                    {
                        "cleaned": True,
                        "mailchimp_last_fetch": fields.Datetime.now(),
                    }
                )
