from functools import wraps

from flask import abort, g
from flask_login import current_user, login_required

from sandik.auth import db


def admin_required(func):
    @wraps(func)
    @login_required
    def decorated_view(*args, **kwargs):
        if not current_user.is_admin():
            abort(401)
        return func(*args, **kwargs)

    return decorated_view


def web_user_required(func):
    @wraps(func)
    def decorated_view(web_user_id, *args, **kwargs):
        web_user = db.get_web_user(id=web_user_id)
        if not web_user:
            abort(404)

        g.web_user = web_user
        return func(web_user_id=web_user_id, *args, **kwargs)

    return decorated_view
