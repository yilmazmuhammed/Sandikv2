from functools import wraps

from flask import abort, g
from flask_login import current_user

from sandik.auth.requirement import login_required
from sandik.sandik import db


def sandik_required(func):
    @wraps(func)
    def decorated_view(sandik_id, *args, **kwargs):
        sandik = db.get_sandik(id=sandik_id)
        if not sandik:
            abort(404)

        g.sandik = sandik
        if current_user.is_authenticated:
            g.member = db.get_member(sandik_ref=g.sandik, web_user_ref=current_user)

        return func(sandik_id=sandik_id, *args, **kwargs)

    return decorated_view


def to_be_member_of_sandik_required(func):
    @wraps(func)
    @login_required
    @sandik_required
    def decorated_view(*args, **kwargs):
        member = db.get_member(sandik_ref=g.sandik, web_user_ref=current_user)
        if not member:
            abort(403, "Bu sandığın üyesi değilsiniz.")

        g.member = member
        return func(*args, **kwargs)

    return decorated_view


def to_be_member_or_manager_of_sandik_required(func):
    @wraps(func)
    @login_required
    @sandik_required
    def decorated_view(*args, **kwargs):
        member = db.get_member(sandik_ref=g.sandik, web_user_ref=current_user)
        if not member and not current_user.has_permission(sandik=g.sandik, permission="read"):
            abort(403, "Bu sayfayı görüntüleme yetkiniz bulunmamaktadır")

        return func(*args, **kwargs)

    return decorated_view


def sandik_authorization_required(permission):
    def sandik_authorization_required_decorator(func):
        @sandik_required
        @login_required
        @wraps(func)
        def decorated_view(*args, **kwargs):
            if not current_user.is_admin() and not current_user.has_permission(sandik=g.sandik, permission=permission):
                abort(403, "Bu sayfaya erişim yetkiniz bulunmamaktadır.")
            return func(*args, **kwargs)

        return decorated_view

    return sandik_authorization_required_decorator


def trust_relationship_required(func):
    @wraps(func)
    def decorated_view(trust_relationship_id, *args, **kwargs):
        trust_relationship = db.get_trust_relationship(id=trust_relationship_id)
        if not trust_relationship:
            abort(404)

        g.trust_relationship = trust_relationship
        return func(trust_relationship_id=trust_relationship_id, *args, **kwargs)

    return decorated_view


def sandik_type_required(sandik_type):
    def sandik_type_required_decorator(func):
        @sandik_required
        @wraps(func)
        def decorated_view(*args, **kwargs):
            if g.sandik.type != sandik_type:
                abort(404, "Bulunduğunuz sandığın sandık türünde bu işlem yapılamamaktadır.")
            return func(*args, **kwargs)

        return decorated_view

    return sandik_type_required_decorator


def sandik_rule_required(func):
    @wraps(func)
    def decorated_view(sandik_rule_id, *args, **kwargs):
        sandik_rule = db.get_sandik_rule(id=sandik_rule_id)
        if not sandik_rule:
            abort(404)

        g.sandik_rule = sandik_rule
        return func(sandik_rule_id=sandik_rule_id, *args, **kwargs)

    return decorated_view
