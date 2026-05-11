"""Minimal BackgroundScheduler used by tests and fallback runtime paths."""


class _Job:
    def __init__(self, *, func, trigger=None, id=None, name=None, replace_existing=False):
        self.func = func
        self.trigger = trigger
        self.id = id
        self.name = name
        self.replace_existing = replace_existing


class BackgroundScheduler:
    def __init__(self, job_defaults=None):
        self.job_defaults = job_defaults or {}
        self.running = False
        self._jobs = []

    def add_job(self, func, trigger=None, id=None, name=None, replace_existing=False, **kwargs):
        if replace_existing and id is not None:
            self._jobs = [job for job in self._jobs if job.id != id]
        self._jobs.append(
            _Job(
                func=func,
                trigger=trigger,
                id=id,
                name=name,
                replace_existing=replace_existing,
            )
        )

    def get_jobs(self):
        return list(self._jobs)

    def start(self):
        self.running = True

    def shutdown(self, wait=True):
        self.running = False
