from functools import wraps

from flask import abort, current_app, request, g
from flask_login import current_user, logout_user
from flask_login.config import EXEMPT_METHODS

from sandik.auth import db


def login_required(func):
    @wraps(func)
    def decorated_view(*args, **kwargs):
        if request.method in EXEMPT_METHODS:
            return func(*args, **kwargs)
        elif current_app.config.get('LOGIN_DISABLED'):
            return func(*args, **kwargs)
        elif not current_user.is_authenticated:
            return current_app.login_manager.unauthorized()
        elif not current_user.is_active:
            logout_user()
            return current_app.login_manager.unauthorized()
        return func(*args, **kwargs)

    return decorated_view


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
        web_user = db.get_web_user(id=kwargs.get("web_user_id"))
        if not web_user:
            abort(404)

        g.web_user = web_user
        return func(web_user_id=web_user_id, *args, **kwargs)

    return decorated_view
