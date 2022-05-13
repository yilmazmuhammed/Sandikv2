import os

import requests as requests

from sandik.bot.netgsm.exceptions import InvalidLanguage

not_latin_characters = {
    ord('ı'): 'i',
    ord('ş'): 's',
    ord('ğ'): 'g',
    ord('ü'): 'u',
    ord('ç'): 'c',
    ord('ö'): 'o',
    ord('İ'): 'I',
    ord('Ş'): 'S',
    ord('Ğ'): 'G',
    ord('Ü'): 'U',
    ord('Ç'): 'C',
    ord('Ö'): 'O',
    ord('\n'): '\\n',
}


class NetGsmXmlApi:
    def __init__(self, usercode, password, appkey=None, default_message_header=None):
        self.company = "Netgsm"
        self.usercode = usercode
        self.password = password
        self.appkey = appkey
        self.default_message_header = default_message_header
        self.languages = ["TR"]
        self.translate_dict = not_latin_characters

    def send_sms(self, message=None, phone_numbers=None, message_packages=None, message_header=None, language="TR"):
        if not message_packages and not message:
            raise Exception("Fill 'message' or 'message_packages'")
        elif message and message_packages:
            raise Exception("Fill only one from 'message' or 'message_packages'")
        if message and not phone_numbers:
            raise Exception("Fill 'phone_numbers' for send 1:n sms")
        if language and language not in self.languages:
            raise InvalidLanguage(f"'{language}' is not valid language.")
        message_header = message_header or self.default_message_header
        if not message_header:
            raise Exception("Fill 'message_header'")
        language_parameter = f'dil="{language}"' if language else ""

        if message:
            message = message.translate(self.translate_dict)
            xml_body = f"""<msg><![CDATA[{message}]]></msg>"""
            for pn in phone_numbers:
                xml_body += f"<no>{pn}</no>"
        else:
            xml_body = ""
            for mp in message_packages:
                xml_body += f"""<mp><msg><![CDATA[{mp["message"].translate(self.translate_dict)}]]></msg><no>{mp["phone_number"]}</no></mp>"""

        url = "https://api.netgsm.com.tr/sms/send/xml"
        payload = f"<?xml version=\"1.0\" encoding=\"UTF-8\"?>\r\n " \
                  f"<mainbody>\r\n " \
                  f"<header>\r\n " \
                  f"<company {language_parameter}>Netgsm</company>        \r\n " \
                  f"<usercode>{self.usercode}</usercode>\r\n " \
                  f"<password>{self.password}</password>\r\n " \
                  f"<type>{'1:n' if message else 'n:n'}</type>\r\n " \
                  f"<msgheader>{message_header}</msgheader>\r\n " \
                  f"</header>\r\n " \
                  f"<body>\r\n " \
                  f"{xml_body}\r\n " \
                  f"</body>\r\n " \
                  f"</mainbody>"
        headers = {'Content-Type': 'application/xml'}
        print(payload)
        response = requests.request("POST", url, headers=headers, data=payload)

        return response


if __name__ == '__main__':
    from datetime import datetime

    netgsm = NetGsmXmlApi(usercode=os.getenv("SMS_BOT_USERCODE"),
                          password=os.getenv("SMS_BOT_PASSWORD"),
                          default_message_header=os.getenv("SMS_BOT_DEFAULT_MESSAGE_HEADER"))
    resp = netgsm.send_sms("qwertyuıopğüasdfghjklşizxcvbnmöç\nQWERTYUIOPĞÜİŞLKJHGFDSAZXCVBNMÖÇ", phone_numbers=["905392024175"])
    print("response:", resp)
    print("response.text:", resp.text)
    # resp = netgsm.send_sms(message_packages=[{"message": "Güven bağı " + str(datetime.now()) + "\\n" + str(datetime.now()),
    #                                           "phone_number": "905392024175"}])
    # print("response:", resp)
    # print("response.text:", resp.text)
