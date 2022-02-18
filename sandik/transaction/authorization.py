from functools import wraps

from flask import g, abort

from sandik.sandik.requirement import sandik_required
from sandik.transaction import db


def money_transaction_required(func):
    @wraps(func)
    @sandik_required
    def decorated_view(*args, **kwargs):

        if not kwargs.get("money_transaction_id"):
            abort(404)

        money_transaction = db.get_money_transaction(id=kwargs.get("money_transaction_id"))
        if not money_transaction or money_transaction.member_ref.sandik_ref != g.sandik:
            abort(404)

        g.money_transaction = money_transaction

        return func(*args, **kwargs)

    return decorated_view
