from functools import wraps

from flask import session, redirect, url_for, g


def kt_login_required(func):
    @wraps(func)
    def decorated_view(*args, **kwargs):
        auth_code = session.get("kt_auth_code")

        if not auth_code:
            return redirect(url_for('kt_page_bp.login_page'))

        g.kt_auth_code = auth_code

        return func(*args, **kwargs)

    return decorated_view
