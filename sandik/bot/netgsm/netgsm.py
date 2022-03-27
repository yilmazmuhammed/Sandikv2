import os
from datetime import datetime

from sandik.bot.netgsm.netgsm_httpget import NetGsmHttpGetApi


class MessagePacket:
    def __init__(self, message, phone_number):
        self.message = message
        self.phone_number = phone_number


class NetGsmApi:
    def __init__(self, usercode, password, appkey=None, default_message_header=None):
        self.company = "Netgsm"
        self.usercode = usercode
        self.password = password
        self.appkey = appkey
        self.http_get_api = NetGsmHttpGetApi(usercode=usercode, password=password,
                                             default_message_header=default_message_header)

    def send_sms(self, message=None, phone_numbers=None, message_packages=None, message_header=None, language="TR"):
        message = message.replace("\n", "\\n")
        if message_packages:
            for mp in message_packages:
                self.http_get_api.send_sms(message=mp["message"], phone_numbers=mp["phone_number"],
                                           message_header=message_header, language=language)
        elif len(phone_numbers) > 1:
            for pn in phone_numbers:
                self.http_get_api.send_sms(message=message, phone_numbers=[pn],
                                           message_header=message_header, language=language)
        else:
            self.http_get_api.send_sms(message=message, phone_numbers=phone_numbers,
                                       message_header=message_header, language=language)


if __name__ == '__main__':
    netgsm = NetGsmApi(usercode=os.getenv("SMS_BOT_USERCODE"),
                       password=os.getenv("SMS_BOT_PASSWORD"),
                       default_message_header=os.getenv("SMS_BOT_DEFAULT_MESSAGE_HEADER"))
    netgsm.send_sms(message=str(datetime.now()), phone_numbers=["905392024175"])
