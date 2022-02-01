import inspect
from datetime import datetime


class ErrcodeException(Exception):
    pass


class Sandikv2Exception(Exception):
    def __init__(self, msg, errcode=1, create_log=False, errcode_thousand=1):
        if not (0 < errcode < 1000):
            raise ErrcodeException()

        self.errcode = errcode_thousand * 1000 + errcode
        self.msg = msg
        self.caller_function_name = "not_detected"
        self.detect_caller_function_name()

        if create_log:
            # TODO print yerine log mekanizması kullan
            print("LOG -> ", datetime.now(), self.exception_message)

        super().__init__(self.exception_message)

    @property
    def exception_message(self):
        return f"ERRCODE: {self.errcode}, FUNCTION: {self.caller_function_name} -> {self.msg}"

    def detect_caller_function_name(self):
        for frame_info in inspect.stack():
            for line in frame_info[4]:
                if "raise" in line:
                    self.caller_function_name = frame_info[3]


class Sandikv2ModuleTemplateException(Sandikv2Exception):
    ERRCODE_THOUSAND = 2

    def __init__(self, msg="", errcode=0, create_log=False):
        super().__init__(msg=msg, errcode=errcode, create_log=create_log, errcode_thousand=self.ERRCODE_THOUSAND)


class InvalidWhoseType(Sandikv2ModuleTemplateException):
    def __init__(self, msg="", errcode=0, create_log=False):
        super().__init__(msg=msg, errcode=errcode, create_log=create_log)


class UnexpectedValue(Sandikv2ModuleTemplateException):
    def __init__(self, msg="", errcode=0, create_log=False):
        super().__init__(msg=msg, errcode=errcode, create_log=create_log)
