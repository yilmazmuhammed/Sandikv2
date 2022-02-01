import inspect
from datetime import datetime

from flask_login import current_user

from sandik.utils.db_models import Log


class THOUSANDS:
    Sandikv2Exception = 1
    Sandikv2UtilsException = 2
    TransactionException = 10
    DebtException = 11
    SandikException = 20
    TrustRelationshipException = 21
    MembershipException = 22


class ErrcodeException(Exception):
    pass


class Sandikv2Exception(Exception):
    ERRCODE_THOUSAND = THOUSANDS.Sandikv2Exception

    def __init__(self, msg, errcode=1, create_log=False, log_level=None, errcode_thousand=ERRCODE_THOUSAND):
        if not (0 < errcode < 1000):
            raise ErrcodeException()

        self.errcode = errcode_thousand * 1000 + errcode
        self.msg = msg
        self.caller_function_name = "not_detected"
        self.exception_class = "not_detected"
        self.detect_caller_function_name()

        if create_log:
            # TODO print yerine log mekanizması kullan
            log_level = log_level or Log.TYPE.LOG_LEVEL.INFO
            Log(web_user_ref=current_user,
                type=log_level, special_type=str(self.errcode), detail=self.exception_message)
            print("LOG -> ", datetime.now(), self.exception_message)

        super().__init__(self.exception_message)

    @property
    def exception_message(self):
        return f"ERRCODE: {self.errcode}, " \
               f"FUNCTION: {self.caller_function_name}, " \
               f"EXCEPTION: {self.exception_class} -> " \
               f"{self.msg}"

    def detect_caller_function_name(self):
        for frame_info in inspect.stack():
            for line in frame_info[4]:
                if "raise" in line:
                    self.caller_function_name = frame_info[3]
                    self.exception_class = frame_info[4].split("(")[0].split("raise")[1].strip()


class Sandikv2UtilsException(Sandikv2Exception):
    ERRCODE_THOUSAND = THOUSANDS.Sandikv2UtilsException

    def __init__(self, msg="", errcode=0, create_log=False, **kwargs):
        super().__init__(msg=msg, errcode=errcode, create_log=create_log, errcode_thousand=self.ERRCODE_THOUSAND,
                         **kwargs)


class InvalidWhoseType(Sandikv2UtilsException):
    pass


class UnexpectedValue(Sandikv2UtilsException):
    pass
