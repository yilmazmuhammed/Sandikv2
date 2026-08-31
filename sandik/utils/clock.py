"""Her gece çalışan dönemsel işler.

PythonAnywhere'de zamanlanmış görev olarak her gece 01:01'de çalışır ve biter. PythonAnywhere web
uygulamalarında thread desteklenmediği ve istek/yanıt döngüsünden uzun yaşayan alt süreçler
öldürüldüğü için, dönemsel işlerin yeri Flask sürecinin içi değil bu betiktir.

Betik her gece çalıştığından, "hangi işin sırası geldi" kararı **burada** verilir:

- Aidat oluşturma her çalıştırmada koşar (idempotenttir, var olan aidatı tekrar oluşturmaz).
- Ödeme hatırlatma e-postaları her kullanıcının **kendi seçtiği günde** gönderilir; gün tam
  eşitlikle karşılaştırıldığı için iş kişi başına ayda bir kez koşar ve mükerrer engeli için kayıt
  tutulmaz (bkz. `sandik/utils/reminder.py`).

**Adımlar birbirinden yalıtılmıştır**: aidat oluşturma patlarsa hata yazılır ama hatırlatma yine
çalışır. Hatırlatmanın tek şansı olduğu için (kaçarsa o ay tekrar denenmez) erken bir hatanın onu
engellememesi gerekir. Herhangi bir adım hata verirse betik sıfırdan farklı çıkar; PythonAnywhere
görev çıktısını e-postayla gönderdiği için arıza görünür olur.

Elle çalıştırma:

    FLASK_DEBUG=1 ../venv/bin/python sandik/utils/clock.py --yardim
"""
import os
import sys
import traceback

from dotenv import load_dotenv

current = os.path.dirname(os.path.realpath(__file__))
parent = os.path.dirname(current)
root = os.path.dirname(parent)

sys.path.append(root)  # import'lardaki sandik.* modülleri için

if os.getenv("FLASK_DEBUG"):
    load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env_debug'))
else:
    load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env'))

from pony.orm import db_session  # noqa: E402  (.env yüklendikten sonra)

from sandik.auth import db as auth_db  # noqa: E402
from sandik.auth import utils as auth_utils  # noqa: E402
from sandik.bot import email_bot  # noqa: E402
from sandik.transaction import utils as transaction_utils  # noqa: E402
from sandik.utils import reminder  # noqa: E402

USAGE = """Kullanım: python sandik/utils/clock.py [seçenekler]

Seçeneksiz çalıştırıldığında gecelik akışın tamamını yürütür:
aidatları oluşturur, sonra günün hangi hatırlatmaları gerektirdiğine bakar.

  --aidat                 Yalnızca vadesi gelmiş aidatları oluştur
  --hatirlatma-ay-basi    Ay başı hatırlatmasını çalıştır (bu ayın ödemeleri)
  --hatirlatma-ay-sonu    Ay sonu hatırlatmasını çalıştır (bu ay + gelecek ay)
                          Bu iki seçenek gün tercihini yok sayar; hatırlatmayı kapatmış
                          kullanıcılara yine gönderilmez.
  --kuru                  Hiçbir e-posta gönderme, kime ne gideceğini yaz
  --html=<dosya>          Üretilen e-postaların HTML'ini bu dosyaya yaz (gözle kontrol için)
  --yardim                Bu metni göster
"""


def beginning_of_each_month():
    # TODO Aidatları ve taksitleri öde
    with db_session:
        # TODO sadece bu ayın aidatlarını oluştur
        transaction_utils.create_due_contributions_for_all_sandiks(
            created_by=auth_db.get_or_create_bot_user(which="clock"),
            created_from="clock.beginning_of_each_month"
        )


def build_app():
    """Şablon basmak ve mutlak adres üretmek için, yalnızca bu sürece ait bir Flask uygulaması.

    `render_template` ve `tr_number_format` filtresi uygulama bağlamı ister; `url_for(_external=True)`
    ise `SERVER_NAME` ister. Web sürecine `SERVER_NAME` verilmez (yönlendirmeyi bozar), bu yüzden
    burada ayrı bir örnek kurulur.
    """
    from sandik.app import create_app

    app = create_app()
    app.config["SERVER_NAME"] = os.getenv("SANDIKv2_SERVER_NAME", "sandikv2.myilmaz.tr")
    # Site her ortamda https yayınlanıyor; e-postadaki bağlantı da hep canlı adrese gitmeli.
    app.config["PREFERRED_URL_SCHEME"] = "https"
    return app


class _LazyEmailSender:
    """SMTP bağlantısını ilk gönderimde açar.

    Betik her gece çalışıp çoğu gece hiç e-posta göndermediği için bağlantı peşinen açılmaz.
    """

    def __init__(self):
        self.bot = None

    def __call__(self, to_address, subject, html):
        if self.bot is None:
            self.bot = email_bot.create_email_bot_from_env()
        email_bot.send_html_email(bot=self.bot, to_address=to_address, subject=subject, html=html)

    def close(self):
        if self.bot is not None:
            self.bot.disconnect_server()
            self.bot = None


def run_reminders(kind=None, dry_run=False, html_path=None):
    """Hatırlatmaları çalıştırır.

    `kind` verilmezse gecelik kip: kimin bugün istediğine `reminder.reminder_for_today` karar verir.
    Verilirse elle kip: gün yok sayılır (bkz. `USAGE`).
    """
    # Kapatma valfi yalnızca gerçek gönderimi durdurur; kuru çalıştırma zaten e-posta göndermez.
    if not dry_run and not reminder.is_enabled():
        print("Hatırlatma e-postaları kapalı (SANDIKv2_REMINDER_EMAIL_ENABLED)")
        return

    from flask import render_template, url_for

    app = build_app()
    sender = _LazyEmailSender()
    rendered_pages = []

    def url_builder(sandik_id):
        return url_for("sandik_page_bp.sandik_summary_for_member_page", sandik_id=sandik_id, _external=True)

    def preference_url_builder(web_user):
        token = auth_utils.create_reminder_preference_token(web_user=web_user)
        return url_for("auth_page_bp.reminder_preference_by_token_page", token=token, _external=True)

    def render(data):
        html = render_template("email/payment_reminder.html", data=data)
        if html_path:
            rendered_pages.append(html)
        return html

    try:
        with app.app_context():
            reminder.run_payment_reminder(
                url_builder=url_builder, preference_url_builder=preference_url_builder,
                render=render, send=sender, kind=kind, dry_run=dry_run,
            )
    finally:
        sender.close()

    if html_path and rendered_pages:
        with open(html_path, "w", encoding="utf-8") as f:
            f.write("<hr>".join(rendered_pages))
        print(f"{len(rendered_pages)} e-postanın HTML'i yazıldı: {html_path}")


def _step(title, func, **kwargs):
    """Bir adımı çalıştırır; patlarsa hatayı yazıp `False` döner, sonraki adım yine koşar.

    Hatırlatmanın ayda tek şansı var (bkz. modül açıklaması); aidat oluşturmadaki bir hata onu
    engellememeli.
    """
    try:
        func(**kwargs)
    except Exception:
        print(f"HATA: {title} adımı tamamlanamadı", file=sys.stderr)
        traceback.print_exc()
        return False
    return True


def main(argv):
    if "--yardim" in argv or "--help" in argv:
        print(USAGE)
        return 0

    dry_run = "--kuru" in argv
    html_path = next((a.split("=", 1)[1] for a in argv if a.startswith("--html=")), None)

    only_contributions = "--aidat" in argv
    month_start = "--hatirlatma-ay-basi" in argv
    next_month = "--hatirlatma-ay-sonu" in argv
    selected_reminder = month_start or next_month

    kinds = []
    if month_start:
        kinds.append(reminder.KIND_MONTH_START)
    if next_month:
        kinds.append(reminder.KIND_NEXT_MONTH)

    failed = False
    if only_contributions or not selected_reminder:
        failed |= not _step("Aidat oluşturma", beginning_of_each_month)

    if not selected_reminder and not only_contributions:
        # Seçeneksiz çağrı: gecelik akış. Kimin bugün mail istediğine kullanıcı tercihleri karar verir.
        failed |= not _step("Hatırlatma e-postaları", run_reminders, dry_run=dry_run, html_path=html_path)
    for kind in kinds:
        failed |= not _step(f"Hatırlatma e-postaları ({kind})", run_reminders, kind=kind,
                            dry_run=dry_run, html_path=html_path)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
