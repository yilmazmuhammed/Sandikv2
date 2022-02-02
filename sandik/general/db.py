from datetime import datetime

from sandik.general.exceptions import ThereIsAlreadyPrimaryBankAccount
from sandik.utils.db_models import BankAccount, Log, Notification


def create_bank_account(created_by, is_primary, **kwargs) -> BankAccount:
    sandik = kwargs.get("sandik_ref")
    web_user = kwargs.get("web_user_ref")
    if is_primary:
        if BankAccount.get(sandik_ref=sandik, web_user_ref=web_user, is_primary=is_primary):
            raise ThereIsAlreadyPrimaryBankAccount(
                f"Aynı anda sadece bir tane birincil (varsayılan) banka hesabı bulunabilir.")
    log = Log(web_user_ref=created_by, type=Log.TYPE.CREATE, logged_sandik_ref=sandik, logged_web_user_ref=web_user)
    return BankAccount(logs_set=log, is_primary=is_primary, **kwargs)


def get_notification(**kwargs) -> Notification:
    return Notification.get(**kwargs)


def get_bank_account(**kwargs) -> BankAccount:
    return BankAccount.get(**kwargs)


def read_notification(notification) -> Notification:
    notification.set(reading_time=datetime.now())
    return notification


def create_notification(to_web_user, title, text, url) -> Notification:
    return Notification(web_user_ref=to_web_user, title=title, text=text, url=url)


def delete_bank_account(bank_account):
    bank_account.delete()
