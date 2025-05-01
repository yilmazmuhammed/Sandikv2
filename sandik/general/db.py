from datetime import datetime

from pony.orm import select

from sandik.general.exceptions import ThereIsAlreadyPrimaryBankAccount
from sandik.utils.db_models import BankAccount, Log, Notification, get_updated_fields, Sandik, WebUser, SubReceipt, \
    Debt, Member


def create_bank_account(created_by, is_primary, **kwargs) -> BankAccount:
    sandik = kwargs.get("sandik_ref")
    web_user = kwargs.get("web_user_ref")
    if is_primary:
        if BankAccount.get(sandik_ref=sandik, web_user_ref=web_user, is_primary=is_primary):
            raise ThereIsAlreadyPrimaryBankAccount(
                "Aynı anda sadece bir tane birincil (varsayılan) banka hesabı bulunabilir.")
    log = Log(web_user_ref=created_by, type=Log.TYPE.BANK_ACCOUNT.CREATE, logged_sandik_ref=sandik,
              logged_web_user_ref=web_user)
    return BankAccount(logs_set=log, is_primary=is_primary, **kwargs)


def create_notification(to_web_user, title, text, url='') -> Notification:
    return Notification(web_user_ref=to_web_user, title=title, text=text, url=url)


def delete_bank_account(bank_account, deleted_by):
    Log(web_user_ref=deleted_by, type=Log.TYPE.BANK_ACCOUNT.DELETE, detail=str(bank_account.to_dict()))
    for log in bank_account.logs_set:
        log.detail += f"deleted_bank_account_id: {bank_account.id}"
    bank_account.delete()


def get_notification(**kwargs) -> Notification:
    return Notification.get(**kwargs)


def get_bank_account(**kwargs) -> BankAccount:
    return BankAccount.get(**kwargs)


def select_logs(**kwargs):
    return Log.select(**kwargs)


def read_notification(notification) -> Notification:
    notification.set(reading_time=datetime.now())
    return notification


def update_bank_account(bank_account, updated_by, **kwargs):
    updated_fields = get_updated_fields(new_values=kwargs, db_object=bank_account)
    Log(web_user_ref=updated_by, type=Log.TYPE.BANK_ACCOUNT.UPDATE, logged_bank_account_ref=bank_account,
        detail=str(updated_fields))
    bank_account.set(**kwargs)
    return bank_account

def get_real_sandiks():
    return [s for s in Sandik.select() if s.is_testing_purposes() == False]

def get_sandik_count():
    return len(get_real_sandiks())


def get_web_user_count():
    return select(m.web_user_ref for m in Member if m.sandik_ref in get_real_sandiks()).count()


def get_total_contribution_amount_of_all_sandiks():
    return select(
        sr.amount for sr in SubReceipt
        if sr.contribution_ref and sr.money_transaction_ref.is_type_revenue() and sr.sandik_ref in get_real_sandiks()
    ).sum()


def get_total_debt_amount_of_all_sandiks():
    return select(d.amount for d in Debt if d.sandik_ref in get_real_sandiks()).sum()


def get_debts_count():
    return Debt.select(lambda d: d.sandik_ref in get_real_sandiks()).count()