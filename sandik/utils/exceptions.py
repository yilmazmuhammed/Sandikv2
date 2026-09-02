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
    SandikAuthorityException = 23
    SmsPackageException = 24
    SandikRuleException = 25
    BankAccountException = 30
    AuthException = 40
    EmailBotException = 50
    EmailServerException = 51
    BackupException = 60


class ErrcodeException(Exception):
    pass


class Sandikv2Exception(Exception):
    ERRCODE_THOUSAND = THOUSANDS.Sandikv2Exception

    def __init__(self, msg, errcode=1, create_log=False, log_level=None, errcode_thousand=ERRCODE_THOUSAND,
                 modify_msg=False):
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
                type=log_level, special_type=str(self.errcode), detail=self.modified_message())
            print("LOG -> ", datetime.now(), self.modified_message())

        if modify_msg:
            super().__init__(self.modified_message())
        else:
            super().__init__(self.msg)

    def modified_message(self):
        return f"{self.msg} " \
               f"(ERRCODE: {self.errcode}, " \
               f"FUNCTION: {self.caller_function_name}, " \
               f"EXCEPTION: {self.exception_class} )"

    def detect_caller_function_name(self):
        for frame_info in inspect.stack():
            # Kaynak kodu okunamayan frame'lerde (exec ile üretilen kod, template vs.) code_context None gelir
            for line in frame_info[4] or []:
                # "raise" kelimesi satırda geçse de bir fırlatma olmayabilir: `pytest.raises(...)`
                # ya da `x.raises(` gibi satırlarda `split` boş liste döndürüp asıl istisnayı
                # IndexError ile maskeliyordu. Bu yüzden yalnızca ayrıştırılabilen satır kullanılır.
                parts = line.split("(")[0].split("raise ")
                if len(parts) > 1:
                    self.caller_function_name = frame_info[3]
                    self.exception_class = parts[1].strip()


class Sandikv2UtilsException(Sandikv2Exception):
    ERRCODE_THOUSAND = THOUSANDS.Sandikv2UtilsException

    # DİKKAT: Sandikv2Exception, errcode için '0 < errcode < 1000' şartı arar. Varsayılan 0
    # bırakılırsa errcode verilmeden fırlatılan her istisna, asıl mesajı kaybederek boş bir
    # ErrcodeException'a dönüşür (ör. ERRCODE 0010/0011).
    def __init__(self, msg="", errcode=1, create_log=False, **kwargs):
        super().__init__(msg=msg, errcode=errcode, create_log=create_log, errcode_thousand=self.ERRCODE_THOUSAND,
                         **kwargs)


class InvalidWhoseType(Sandikv2UtilsException):
    pass


class UnexpectedValue(Sandikv2UtilsException):
    pass
