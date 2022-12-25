from sandik.sandik.exceptions import SandikException
from sandik.utils.exceptions import THOUSANDS


class EmailBotException(SandikException):
    ERRCODE_THOUSAND = THOUSANDS.EmailBotException

    def __init__(self, msg="", errcode=1, create_log=False, **kwargs):
        super().__init__(msg=msg, errcode=errcode, create_log=create_log,
                         errcode_thousand=kwargs.pop("errcode_thousand", self.ERRCODE_THOUSAND),
                         **kwargs)


class ServerConnectionException(EmailBotException):
    ERRCODE_THOUSAND = THOUSANDS.EmailServerException

    def __init__(self, msg="", errcode=1, create_log=False, **kwargs):
        super().__init__(msg=msg, errcode=errcode, create_log=create_log,
                         errcode_thousand=kwargs.pop("errcode_thousand", self.ERRCODE_THOUSAND),
                         **kwargs)


class DisconnectServerException(ServerConnectionException):
    ERRCODE = 101

    def __init__(self, msg="", create_log=False, **kwargs):
        super().__init__(msg=msg, create_log=create_log,
                         errcode=kwargs.pop("errcode", self.ERRCODE),
                         errcode_thousand=kwargs.pop("errcode_thousand", self.ERRCODE_THOUSAND),
                         **kwargs)


class ServerDisconnected(ServerConnectionException):
    ERRCODE = 102

    def __init__(self, msg="", create_log=False, **kwargs):
        super().__init__(msg=msg, create_log=create_log,
                         errcode=kwargs.pop("errcode", self.ERRCODE),
                         errcode_thousand=kwargs.pop("errcode_thousand", self.ERRCODE_THOUSAND),
                         **kwargs)


class AuthenticationError(ServerConnectionException):
    ERRCODE = 103

    def __init__(self, msg="", create_log=False, **kwargs):
        super().__init__(msg=msg, create_log=create_log,
                         errcode=kwargs.pop("errcode", self.ERRCODE),
                         errcode_thousand=kwargs.pop("errcode_thousand", self.ERRCODE_THOUSAND),
                         **kwargs)


class SenderRefused(EmailBotException):
    ERRCODE = 201

    def __init__(self, msg="", create_log=False, **kwargs):
        super().__init__(msg=msg, create_log=create_log,
                         errcode=kwargs.pop("errcode", self.ERRCODE),
                         errcode_thousand=kwargs.pop("errcode_thousand", self.ERRCODE_THOUSAND),
                         **kwargs)


class RepetitionsAreOver(EmailBotException):
    ERRCODE = 202

    def __init__(self, msg="", create_log=False, **kwargs):
        super().__init__(msg=msg, create_log=create_log,
                         errcode=kwargs.pop("errcode", self.ERRCODE),
                         errcode_thousand=kwargs.pop("errcode_thousand", self.ERRCODE_THOUSAND),
                         **kwargs)


