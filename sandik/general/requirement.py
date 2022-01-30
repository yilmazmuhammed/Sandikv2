from functools import wraps

from flask import abort, g
from flask_login import current_user

from sandik.auth.requirement import login_required
from sandik.general import db


def notification_required(func):
    @wraps(func)
    @login_required
    def decorated_view(*args, **kwargs):

        if not kwargs.get("notification_id"):
            abort(404)

        notification = db.get_notification(id=kwargs.get("notification_id"))
        if not notification:
            abort(404)

        if notification.web_user_ref != current_user:
            abort(403)

        g.notification = notification
        return func(*args, **kwargs)

    return decorated_view
