"""E-posta gönderimi: ham SMTP sarmalayıcısı ve onun üstündeki tek giriş kapısı.

`SenderEmail`/`EmailBot` alt seviyedir. Uygulama kodu bunları doğrudan kurmak yerine dosyanın
sonundaki yardımcıları kullanır; bunlar iki şeyi standartlaştırır:

- **Ayarların tek yerden okunması.** `SANDIKv2_EMAIL_BOT_*` anahtarları başka hiçbir yerde
  `os.getenv` ile okunmamalıdır.
- **Her mesajda tek alıcı.** `EmailBot.create_email_message` verilen adresleri virgülle birleştirip
  `To:` başlığına koyar; toplu gönderimde bu, bütün üyelerin adreslerini birbirine gösterir.
  `send_html_email` tek bir adres alır, bu yüzden böyle bir sızıntı mümkün değildir.

Toplu iş (ör. aylık hatırlatma) için `email_bot_session()` kullanılır: tek bağlantı açılır, bütün
mesajlar onun üzerinden gider, sonunda kapatılır.
"""
import os
import smtplib
from contextlib import contextmanager
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from time import sleep

from sandik.bot.exceptions import DisconnectServerException, ServerDisconnected, AuthenticationError, SenderRefused, \
    RepetitionsAreOver


class SenderEmail:
    def __init__(self, email_address: str, password: str, smtp_server: str = None, display_name: str = None):
        self.email_address = email_address
        self.from_addr = email_address
        self.password = password

        if smtp_server:
            self.smtp_server = smtp_server
        else:
            self.smtp_server = self.smtpserver_finder(self.email_address)

        if display_name:
            self.display_name = display_name
        else:
            self.display_name = email_address

    @staticmethod
    def smtpserver_finder(email_address: str):
        if email_address.endswith("gmail.com"):
            return "smtp.gmail.com:587"
        elif email_address.endswith("itu.edu.tr"):
            return "outgoing.itu.edu.tr:587"
        elif email_address.endswith("outlook.com"):
            return "smtp.office365.com:587"
        else:
            return ""

    def to_dict(self):
        return {
            "email_address": self.email_address,
            "password": self.password,
            "smtp_server": self.smtp_server,
            "display_name": self.display_name,
        }


class EmailBot:
    def __init__(self, email_address, password, display_name, smtp_server=None):
        self.sender = SenderEmail(email_address=email_address, password=password,
                                  smtp_server=smtp_server, display_name=display_name)
        self.server = None
        self.connect_server()

    def connect_server(self):
        server = smtplib.SMTP(self.sender.smtp_server)
        server.starttls()
        server.login(self.sender.email_address, self.sender.password)
        self.server = server

    def disconnect_server(self):
        try:
            self.server.quit()
        except Exception as e:
            DisconnectServerException(str(e), create_log=True)

    def create_email_message(self, to_addresses: list, subject: str, message: str, message_type="html"):
        if isinstance(to_addresses, str):
            to_addresses = [to_addresses]

        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = formataddr((str(Header(self.sender.display_name, 'utf-8')), self.sender.email_address))
        body = MIMEText(message, message_type)
        msg["To"] = ','.join(to_addresses)
        msg.attach(body)

        return msg

    def send_email(self, to_addresses: list, msg: MIMEMultipart(), trials_remaining=5):
        if isinstance(to_addresses, str):
            to_addresses = [to_addresses]

        try:
            self.server.sendmail(self.sender.email_address, to_addresses, msg.as_string())
            return True
        except smtplib.SMTPServerDisconnected as e:
            ServerDisconnected(str(e), create_log=True)
            self.connect_server()
        except smtplib.SMTPAuthenticationError as e:
            raise AuthenticationError(str(e), create_log=True)
        except smtplib.SMTPSenderRefused as e:
            SenderRefused(str(e), create_log=True)
            sleep(60)

        if trials_remaining > 0:
            return self.send_email(to_addresses=to_addresses, msg=msg, trials_remaining=trials_remaining - 1)
        else:
            raise RepetitionsAreOver("E-posta'yı tekrar göndermeyi deneme sayısı tükendi", create_log=True)


# --- Uygulamanın kullandığı giriş kapısı ---------------------------------------------------

def create_email_bot_from_env() -> EmailBot:
    """Ortam değişkenlerinden bir `EmailBot` kurar. Bağlantı `EmailBot.__init__` içinde açılır."""
    email_address = os.getenv("SANDIKv2_EMAIL_BOT_EMAIL_ADDRESS")
    password = os.getenv("SANDIKv2_EMAIL_BOT_PASSWORD")
    if not email_address or not password:
        raise ValueError("E-posta gönderimi için SANDIKv2_EMAIL_BOT_EMAIL_ADDRESS ve "
                         "SANDIKv2_EMAIL_BOT_PASSWORD tanımlı olmalıdır")
    return EmailBot(
        email_address=email_address,
        password=password,
        smtp_server=os.getenv("SANDIKv2_EMAIL_BOT_SMTP_SERVER"),
        display_name=os.getenv("SANDIKv2_EMAIL_BOT_DISPLAY_NAME"),
    )


@contextmanager
def email_bot_session():
    """Tek bağlantı açıp iş bitince kapatır. Çok sayıda mesaj gönderilecekse bunu kullanın."""
    bot = create_email_bot_from_env()
    try:
        yield bot
    finally:
        bot.disconnect_server()


def send_html_email(bot: EmailBot, to_address: str, subject: str, html: str):
    """Tek bir adrese HTML e-posta gönderir."""
    if not isinstance(to_address, str):
        raise ValueError("send_html_email tek bir adres alır; toplu gönderimde her alıcı için "
                         "ayrı çağrılmalıdır (adreslerin birbirine görünmemesi için)")
    msg = bot.create_email_message(to_addresses=to_address, subject=subject, message=html,
                                   message_type="html")
    return bot.send_email(to_addresses=to_address, msg=msg)


def send_single_html_email(to_address: str, subject: str, html: str):
    """Tek seferlik gönderim: bağlantıyı açar, gönderir, kapatır."""
    with email_bot_session() as bot:
        return send_html_email(bot=bot, to_address=to_address, subject=subject, html=html)


if __name__ == '__main__':
    sender_email = ""
    sender_password = ""
    to_email = ""
    bot = EmailBot(email_address=sender_email, password=sender_password, display_name="Görünen isim")
    msg = bot.create_email_message(to_addresses=[to_email], subject="Konu",
                                   message="<h1>sa</h1>", message_type="html")
    bot.send_email([to_email], msg=msg)
    bot.disconnect_server()
