from functools import wraps

from flask import g, abort

from sandik.sandik.requirement import sandik_required
from sandik.transaction import db


def money_transaction_required(func):
    @wraps(func)
    @sandik_required
    def decorated_view(*args, **kwargs):

        if not kwargs.get("money_transaction_id"):
            abort(404, "'money_transaction_id' parametresinin doldurulması gerekmektedir.")

        money_transaction = db.get_money_transaction(id=kwargs.get("money_transaction_id"))
        if not money_transaction or money_transaction.member_ref.sandik_ref != g.sandik:
            abort(404, "Para giriş/çıkış işlemi bulunamadı.")

        g.money_transaction = money_transaction

        return func(*args, **kwargs)

    return decorated_view


def contribution_required(func):
    @wraps(func)
    @sandik_required
    def decorated_view(*args, **kwargs):

        if not kwargs.get("contribution_id"):
            abort(404, "'contribution_id' parametresinin doldurulması gerekmektedir.")

        contribution = db.get_contribution(id=kwargs.get("contribution_id"))
        if not contribution or contribution.member_ref.sandik_ref != g.sandik:
            abort(404, "Aidat bulunamadı.")

        g.contribution = contribution

        return func(*args, **kwargs)

    return decorated_view
