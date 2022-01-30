class BankAccountException(Exception):
    pass


class ThereIsAlreadyPrimaryBankAccount(BankAccountException):
    pass
