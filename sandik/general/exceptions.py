from sandik.utils.exceptions import Sandikv2Exception, THOUSANDS


class BankAccountException(Sandikv2Exception):
    ERRCODE_THOUSAND = THOUSANDS.BankAccountException

    def __init__(self, msg="", errcode=1, create_log=False, **kwargs):
        super().__init__(msg=msg, errcode=errcode, create_log=create_log, errcode_thousand=self.ERRCODE_THOUSAND,
                         **kwargs)


class ThereIsAlreadyPrimaryBankAccount(BankAccountException):
    pass


class BankAccountNotFound(BankAccountException):
    pass


class PrimaryBankAccountCannotBeDeleted(BankAccountException):
    pass
