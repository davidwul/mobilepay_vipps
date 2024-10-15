from odoo import models


class ScheduleMailing(models.TransientModel):
    _inherit = "mailing.mailing.schedule.date"

    def set_schedule_date(self):
        super().set_schedule_date()
        queue_cron = self.env.ref("mass_mailing.ir_cron_mass_mailing_queue").sudo()
        if queue_cron.nextcall > self.schedule_date:
            queue_cron.write(
                {
                    "nextcall": self.schedule_date,
                    "active": True,
                }
            )
