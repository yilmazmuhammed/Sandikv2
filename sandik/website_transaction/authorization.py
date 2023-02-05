from flask import abort, g
from functools import wraps

from sandik.website_transaction import db


def website_transaction_required(func):
    @wraps(func)
    def decorated_view(website_transaction_id, *args, **kwargs):
        website_transaction = db.get_website_transaction(id=website_transaction_id)
        if not website_transaction:
            abort(404)

        g.website_transaction = website_transaction
        return func(website_transaction_id=website_transaction_id, *args, **kwargs)

    return decorated_view
