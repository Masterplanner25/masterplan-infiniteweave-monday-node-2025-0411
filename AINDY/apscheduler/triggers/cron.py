"""Minimal CronTrigger implementation."""


class CronTrigger:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    @classmethod
    def from_crontab(cls, expression: str):
        parts = str(expression or "").split()
        if len(parts) != 5:
            raise ValueError("Wrong number of fields; got %d, expected 5" % len(parts))
        minute, hour, day, month, day_of_week = parts
        return cls(
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
        )
