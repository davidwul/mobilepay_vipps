from odoo import api, models

from ..tools.date_convert import mailchimp_date_to_datetime


class MailingTrace(models.Model):
    _inherit = "mailing.trace"

    @api.model
    def mailchimp_update_trace(self, email_activity, mass_mailing):
        """
        Update the mailing trace with the MailChimp report.
        @param email_activity: MailChimp report from a specific email
        @param mass_mailing: mailing.mailing record
        @return: True if the trace has been updated, False otherwise
        """
        email = email_activity.get("email_address")
        contact = self.env["mailing.contact"].search(
            [
                ("email", "=", email),
                (
                    "list_ids.mailchimp_list_id",
                    "=",
                    mass_mailing.contact_list_ids.mailchimp_list_id,
                ),
            ],
            limit=1,
        )
        base_vals = {
            "mass_mailing_id": mass_mailing.id,
            "email": email,
            "model": contact._name if contact else mass_mailing._name,
            "res_id": contact.id if contact else mass_mailing.id,
            "sent_datetime": mass_mailing.sent_date,
        }
        trace = self.search(
            [
                ("mass_mailing_id", "=", mass_mailing.id),
                ("email", "=", email),
                ("model", "=", base_vals["model"]),
                ("res_id", "=", base_vals["res_id"]),
            ]
        )
        if not trace:
            trace = self.create(base_vals)
        activities = email_activity.get("activity", [])
        (
            opened,
            clicked,
            bounced,
        ) = [], [], []
        for activity in activities:
            if activity["action"] == "open":
                opened.append(mailchimp_date_to_datetime(activity["timestamp"]))
            elif activity["action"] == "click":
                clicked.append(mailchimp_date_to_datetime(activity["timestamp"]))
                url = activity["url"]
                ip = activity["ip"]
                link_tracker = self.env["link.tracker"].search(
                    [
                        ("url", "=", url),
                        ("mass_mailing_id", "=", mass_mailing.id),
                        ("campaign_id", "=", mass_mailing.campaign_id.id),
                        ("medium_id", "=", mass_mailing.medium_id.id),
                        ("source_id", "=", mass_mailing.source_id.id),
                    ]
                )
                if not link_tracker:
                    link_tracker = self.env["link.tracker"].create(
                        {
                            "url": url,
                            "mass_mailing_id": mass_mailing.id,
                            "campaign_id": mass_mailing.campaign_id.id,
                            "medium_id": mass_mailing.medium_id.id,
                            "source_id": mass_mailing.source_id.id,
                        }
                    )
                link_click = self.env["link.tracker.click"].search(
                    [
                        ("link_id", "=", link_tracker.id),
                        ("ip", "=", ip),
                    ]
                )
                if not link_click:
                    link_click.create(
                        {
                            "link_id": link_tracker.id,
                            "ip": ip,
                            "mailing_trace_id": trace.id,
                            "mass_mailing_id": mass_mailing.id,
                            "create_date": clicked[-1],
                        }
                    )
            elif activity["action"] == "bounce":
                bounced.append(mailchimp_date_to_datetime(activity["timestamp"]))
        if activities:
            mailing_trace_vals = {}
            if opened:
                mailing_trace_vals["open_datetime"] = max(opened)
                mailing_trace_vals["trace_status"] = "open"
            if clicked:
                mailing_trace_vals["links_click_datetime"] = max(clicked)
                mailing_trace_vals["trace_status"] = "open"
            if bounced:
                mailing_trace_vals["failure_type"] = "mail_bounce"
            trace.write(mailing_trace_vals)
        return True
