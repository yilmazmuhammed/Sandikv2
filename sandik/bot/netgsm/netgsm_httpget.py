import os

import requests as requests

from sandik.bot.netgsm.exceptions import InvalidLanguage


class NetGsmHttpGetApi:
    def __init__(self, usercode, password, appkey=None, default_message_header=None):
        self.company = "Netgsm"
        self.usercode = usercode
        self.password = password
        self.appkey = appkey
        self.default_message_header = default_message_header
        self.languages = ["TR"]

    def send_sms(self, message=None, phone_numbers=None, message_packages=None, message_header=None, language="TR"):
        if not message:
            raise Exception("'message' cannot be empty")
        if message_packages or len(phone_numbers) > 1:
            raise Exception("NetGsmHttpGetApi does not support multi-send")
        elif len(phone_numbers) != 1:
            raise Exception("You can send only one phone number")
        if language and language not in self.languages:
            raise InvalidLanguage(f"'{language}' is not valid language.")
        message_header = message_header or self.default_message_header
        if not message_header:
            raise Exception("Fill 'message_header'")

        api_url = 'https://api.netgsm.com.tr/sms/send/get'
        response = requests.get(
            api_url,
            params={
                'usercode': self.usercode, 'password': self.password,
                'msgheader': message_header, 'message': message.replace("\n", "\\n"), 'gsmno': phone_numbers[0],
                "language": language
            },
        )
        return response


if __name__ == '__main__':
    netgsm = NetGsmHttpGetApi(usercode=os.getenv("SMS_BOT_USERCODE"),
                              password=os.getenv("SMS_BOT_PASSWORD"),
                              default_message_header=os.getenv("SMS_BOT_DEFAULT_MESSAGE_HEADER"))
    response = netgsm.send_sms("mesaj \n1", phone_numbers=["905392024175"])
    print("Response:", response)
    print("R text:", response.text)
