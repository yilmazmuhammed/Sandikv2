from sandik.sandik.exceptions import SandikException
from sandik.utils.exceptions import THOUSANDS


class AuthException(SandikException):
    ERRCODE_THOUSAND = THOUSANDS.AuthException

    def __init__(self, msg="", errcode=1, create_log=False, **kwargs):
        super().__init__(msg=msg, errcode=errcode, create_log=create_log,
                         errcode_thousand=kwargs.pop("errcode_thousand", self.ERRCODE_THOUSAND),
                         **kwargs)


class RegisterException(AuthException):
    ERRCODE = 101

    def __init__(self, msg="", create_log=False, **kwargs):
        super().__init__(msg=msg, create_log=create_log,
                         errcode=kwargs.pop("ERRCODE", self.ERRCODE),
                         errcode_thousand=kwargs.pop("errcode_thousand", self.ERRCODE_THOUSAND),
                         **kwargs)


class EmailAlreadyExist(RegisterException):
    ERRCODE = 102

    def __init__(self, msg="", create_log=False, **kwargs):
        super().__init__(msg=msg, create_log=create_log,
                         errcode=kwargs.pop("ERRCODE", self.ERRCODE),
                         errcode_thousand=kwargs.pop("errcode_thousand", self.ERRCODE_THOUSAND),
                         **kwargs)


class WebUserNotFound(AuthException):
    ERRCODE = 201

    def __init__(self, msg="", create_log=False, **kwargs):
        super().__init__(msg=msg, create_log=create_log,
                         errcode=kwargs.pop("ERRCODE", self.ERRCODE),
                         errcode_thousand=kwargs.pop("errcode_thousand", self.ERRCODE_THOUSAND),
                         **kwargs)
