# # -*- coding: utf-8 -*-
from pytz import timezone
from functools import partial
from odoo.addons.resource.models.resource import make_aware, Intervals
from datetime import timedelta
from odoo.tools.float_utils import float_compare
from odoo import models, fields, api, _

class MrpWorkcenter(models.Model):
    _inherit = 'mrp.workcenter'
    
    # override method: go backward from last mo - last wo -> first mo - first wo. 
    def _get_reversed_first_available_slot(self, finish_datetime, duration):
        self.ensure_one()
        finish_datetime, revert = make_aware(finish_datetime)

        get_available_intervals = partial(self.resource_calendar_id._work_intervals, domain=[('time_type', 'in', ['other', 'leave'])], resource=self.resource_id, tz=timezone(self.resource_calendar_id.tz))
        get_workorder_intervals = partial(self.resource_calendar_id._leave_intervals, domain=[('time_type', '=', 'other')], resource=self.resource_id, tz=timezone(self.resource_calendar_id.tz))
        
        remaining = duration
        # start_interval = finish_datetime - timedelta(minutes=duration)
        end_interval = finish_datetime
        delta = timedelta(days=7)

        for n in range(50):  # 50 * 14 = 700 days in advance (hardcoded)
            dt = finish_datetime - delta * n
            available_intervals = get_available_intervals(dt - delta, dt)
            workorder_intervals = get_workorder_intervals(dt - delta, dt)
            for start, stop, dummy in reversed(available_intervals):
                interval_minutes = (stop - start).total_seconds() / 60
                # If the remaining minutes has never decrease update start_interval
                if remaining == duration:
                    end_interval = stop
                # If there is a overlap between the possible available interval and a others WO
                if Intervals([(end_interval - timedelta(minutes=min(remaining, interval_minutes)), stop, dummy)]) & workorder_intervals:
                    remaining = duration
                    end_interval = stop
                elif float_compare(interval_minutes, remaining, precision_digits=3) >= 0:
                    return revert(stop - timedelta(minutes=remaining)), revert(end_interval)
                # Decrease a part of the remaining duration
                remaining -= interval_minutes
        return False, 'Not available slot 700 days before'