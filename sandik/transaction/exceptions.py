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
