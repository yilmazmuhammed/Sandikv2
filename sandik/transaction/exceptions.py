from sandik.utils.exceptions import Sandikv2Exception, THOUSANDS


class TransactionException(Sandikv2Exception):
    ERRCODE_THOUSAND = THOUSANDS.TransactionException

    def __init__(self, msg="", errcode=1, create_log=False, **kwargs):
        super().__init__(msg=msg, errcode=errcode, create_log=create_log,
                         errcode_thousand=kwargs.pop("errcode_thousand", self.ERRCODE_THOUSAND),
                         **kwargs)


class DebtException(TransactionException):
    ERRCODE_THOUSAND = THOUSANDS.DebtException

    def __init__(self, msg="", errcode=1, create_log=False, **kwargs):
        super().__init__(msg=msg, errcode=errcode, create_log=create_log,
                         errcode_thousand=kwargs.pop("errcode_thousand", self.ERRCODE_THOUSAND),
                         **kwargs)


class MaximumDebtAmountExceeded(DebtException):
    pass


class MaximumInstallmentExceeded(DebtException):
    pass


class InvalidStartingTerm(DebtException):
    pass


class UndefinedRemoveOperation(TransactionException):
    pass


class InvalidRemoveOperation(TransactionException):
    pass


class ThereIsNoDebt(TransactionException):
    pass


class MaximumAmountExceeded(TransactionException):
    pass


class UndefinedMoneyTransactionValidation(TransactionException):
    pass


class InvalidMoneyTransactionValidation(TransactionException):
    pass
