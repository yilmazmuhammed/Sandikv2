import os

from sandik.bot.netgsm.netgsm import NetGsmApi
from sandik.utils.db_models import SmsPackage


class SmsBot:
    def __init__(self):
        if not os.getenv("SMS_BOT_PROVIDER"):
            raise Exception("'SMS_BOT_PROVIDER' is unspecified")
        elif os.getenv("SMS_BOT_PROVIDER") == "NETGSM":
            self.api_provider = NetGsmApi(
                usercode=os.getenv("SMS_BOT_USERCODE"),
                password=os.getenv("SMS_BOT_PASSWORD"),
                default_message_header=os.getenv("SMS_BOT_DEFAULT_MESSAGE_HEADER")
            )
        else:
            raise Exception("'SMS_BOT_PROVIDER' is not valid")

    def send_sms_package(self, sms_package: SmsPackage):
        kwargs = {"message_header": sms_package.header}
        if sms_package.is_n_to_n():
            message_packages = []
            for wu in sms_package.web_users_set:
                if wu.phone_number:
                    text = sms_package.text.format(name_surname=wu.name_surname)
                    message_packages.append({"message": text, "phone_number": wu.phone_number})
            kwargs["message_packages"] = message_packages
        else:
            kwargs["message"] = sms_package.text
            kwargs["phone_numbers"] = [wu.phone_number for wu in sms_package.web_users_set if wu.phone_number]
        return self.api_provider.send_sms(**kwargs)
