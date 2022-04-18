import os
from datetime import datetime

from sandik.bot.netgsm.netgsm_httpget import NetGsmHttpGetApi
from sandik.bot.netgsm.netgsm_xml import NetGsmXmlApi


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
        self.xml_api = NetGsmXmlApi(usercode=usercode, password=password,
                                    default_message_header=default_message_header)

    def send_sms(self, message=None, phone_numbers=None, message_packages=None, message_header=None, language="TR"):
        if message_packages:
            response = self.xml_api.send_sms(message_packages=message_packages,
                                             message_header=message_header, language=language)
        elif len(phone_numbers) > 1:
            response = self.xml_api.send_sms(message=message, phone_numbers=phone_numbers,
                                             message_header=message_header, language=language)
        else:
            response = self.http_get_api.send_sms(message=message, phone_numbers=phone_numbers,
                                                  message_header=message_header, language=language)
        return response


if __name__ == '__main__':
    netgsm = NetGsmApi(usercode=os.getenv("SMS_BOT_USERCODE"),
                       password=os.getenv("SMS_BOT_PASSWORD"),
                       default_message_header=os.getenv("SMS_BOT_DEFAULT_MESSAGE_HEADER"))
    resp = netgsm.send_sms(message=str(datetime.now()) + "\n asdasdas", phone_numbers=["905392024175"])
    print("response:", resp)
    print("response.text:", resp.text)
    resp = netgsm.send_sms(message_packages=[{"message": str(datetime.now()) + "\\n asdasdas", "phone_number": "905392024175"}])
    print("response:", resp)
    print("response.text:", resp.text)
