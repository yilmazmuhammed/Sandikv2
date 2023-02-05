from functools import wraps

from flask import abort, g
from flask_login import current_user

from sandik.auth.requirement import login_required
from sandik.general import db


def notification_required(func):
    @wraps(func)
    @login_required
    def decorated_view(notification_id, *args, **kwargs):
        notification = db.get_notification(id=notification_id)
        if not notification:
            abort(404, "Bildirim bulunamadı")

        if notification.web_user_ref != current_user:
            abort(403, "Bu bildirimi size ait değildir.")

        g.notification = notification
        return func(notification_id=notification_id, *args, **kwargs)

    return decorated_view
