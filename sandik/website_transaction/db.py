from pony.orm import select, desc

from sandik.utils.db_models import WebsiteTransaction, Log


def get_categories():
    return sorted(select(wt.category for wt in WebsiteTransaction).distinct())


def create_website_transaction(web_user_ref, created_by, **kwargs) -> WebsiteTransaction:
    log = Log(web_user_ref=created_by, type=Log.TYPE.WEBSITE_TRANSACTION.CREATE,
              logged_web_user_ref=web_user_ref)
    return WebsiteTransaction(logs_set=log, web_user_ref=web_user_ref, **kwargs)


def delete_website_transaction(website_transaction, deleted_by):
    Log(web_user_ref=deleted_by, type=Log.TYPE.WEBSITE_TRANSACTION.DELETE, detail=str(website_transaction.to_dict()))
    for log in website_transaction.logs_set:
        log.detail += f"deleted_website_transaction_id: {website_transaction.id}"
    website_transaction.delete()


def get_website_transaction(*args, **kwargs):
    return WebsiteTransaction.get(*args, **kwargs)


def select_website_transactions(*args, **kwargs):
    return WebsiteTransaction.select(*args, **kwargs).order_by(lambda wt: desc(wt.date))


def sum_of_website_transactions():
    return select(wt.amount for wt in WebsiteTransaction if wt.type == WebsiteTransaction.TYPE.REVENUE).sum() - select(
        wt.amount for wt in WebsiteTransaction if wt.type == WebsiteTransaction.TYPE.EXPENSE).sum()
