from functools import wraps

from flask import abort, g

from sandik.form import db


def form_required(func):
    @wraps(func)
    def decorated_view(*args, **kwargs):

        if not kwargs.get("form_id"):
            abort(404)
        form = db.get_form(id=kwargs.get("form_id"))
        if not form:
            abort(404)
        g.form = form
        return func(*args, **kwargs)

    return decorated_view


def form_response_required(func):
    @wraps(func)
    @form_required
    def decorated_view(*args, **kwargs):

        if not kwargs.get("form_response_id"):
            abort(404)
        form_response = db.get_form_response(id=kwargs.get("form_response_id"), form_ref=g.form)
        if not form_response:
            abort(404)
        g.form_response = form_response
        return func(*args, **kwargs)

    return decorated_view
