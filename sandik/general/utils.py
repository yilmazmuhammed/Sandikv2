from sandik.general import db
from sandik.general.exceptions import BankAccountNotFound, PrimaryBankAccountCannotBeDeleted


def remove_bank_account(bank_account_id):
    bank_account = db.get_bank_account(id=bank_account_id)
    if not bank_account:
        raise BankAccountNotFound("Banka hesabı bulunamadı.", create_log=True)

    if bank_account.is_primary:
        raise PrimaryBankAccountCannotBeDeleted("Birincil banka hesabı silinemez")

    return db.delete_bank_account(bank_account=bank_account)
