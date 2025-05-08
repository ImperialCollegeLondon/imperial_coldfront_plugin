"""Plugin tasks."""

from functools import wraps

from django_q.tasks import async_task


def run_in_background(func):
    """Wrapper to run a function.

    Note that Django q's architecture means this can't be used as a straight decorator
    and it's output must be stored as a different name from the wrapped function.
    """

    @wraps(func)
    def wrapped(*args, **kwargs):
        return async_task(func, *args, **kwargs)

    return wrapped
