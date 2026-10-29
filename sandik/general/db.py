from datetime import datetime

from pony.orm import select

from sandik.general.exceptions import ThereIsAlreadyPrimaryBankAccount
from sandik.utils.db_models import BankAccount, Log, Notification, get_updated_fields, MoneyTransaction, Retracted, \
    Contribution, Installment, SubReceipt


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


# --- Mil sonu geçmişi (bkz. general/utils.py -> get_mile_end_history) ---
# Her sorgu, verilen üyelerin hepsi için tek seferde çalışır; satırlar düz demetlerdir. Demetlerin
# başındaki kimlik bilerek seçilir: Pony, birincil anahtar içermeyen demet sorgularına DISTINCT ekler
# ve aynı gün aynı tutardaki iki kayıt teke inerdi.

def select_revenue_money_transaction_rows(member_ids):
    """(id, member_id, tarih, tutar)"""
    return select((mt.id, mt.member_ref.id, mt.date, mt.amount) for mt in MoneyTransaction
                  if mt.member_ref.id in member_ids and mt.type == MoneyTransaction.TYPE.REVENUE)[:]


def select_retracted_rows(member_ids):
    """(id, member_id, iadenin yapıldığı para çıkışının tarihi, gelir işleminden düşülen tutar)"""
    return select((r.id, r.revenue_sub_receipt_ref.money_transaction_ref.member_ref.id,
                   r.expense_sub_receipt_ref.money_transaction_ref.date, r.revenue_sub_receipt_ref.amount)
                  for r in Retracted
                  if r.revenue_sub_receipt_ref.money_transaction_ref.member_ref.id in member_ids)[:]


def select_contribution_rows(member_ids):
    """(id, member_id, dönem, tutar)"""
    return select((c.id, c.share_ref.member_ref.id, c.term, c.amount) for c in Contribution
                  if c.share_ref.member_ref.id in member_ids)[:]


def select_installment_rows(member_ids):
    """(id, member_id, borcun verildiği para çıkışının tarihi, tutar)"""
    return select((i.id, i.debt_ref.share_ref.member_ref.id, i.debt_ref.sub_receipt_ref.money_transaction_ref.date,
                   i.amount) for i in Installment
                  if i.debt_ref.share_ref.member_ref.id in member_ids)[:]


def select_contribution_payment_rows(member_ids):
    """Aidatlara yapılan ödemeler: (id, member_id, aidatın dönemi, para işleminin tarihi, oluşturulma anı, tutar)"""
    return select((sr.id, sr.contribution_ref.share_ref.member_ref.id, sr.contribution_ref.term,
                   sr.money_transaction_ref.date, sr.creation_time, sr.amount) for sr in SubReceipt
                  if sr.contribution_ref.share_ref.member_ref.id in member_ids)[:]


def select_installment_payment_rows(member_ids):
    """Taksitlere yapılan ödemeler:
    (id, member_id, borcun verildiği para çıkışının tarihi, para işleminin tarihi, oluşturulma anı, tutar)"""
    return select((sr.id, sr.installment_ref.debt_ref.share_ref.member_ref.id,
                   sr.installment_ref.debt_ref.sub_receipt_ref.money_transaction_ref.date,
                   sr.money_transaction_ref.date, sr.creation_time, sr.amount) for sr in SubReceipt
                  if sr.installment_ref.debt_ref.share_ref.member_ref.id in member_ids)[:]
