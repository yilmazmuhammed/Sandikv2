"""Üyelere aylık ödeme hatırlatma e-postası gönderen iş.

`clock.py` her gece çalışır. Bu modül "bugün kime hatırlatma gönderilmeli" sorusunu cevaplar ve
gönderimi yürütür. İki hatırlatma vardır:

- **Ay başı**: geçmiş aylardan kalan + bu ayın ödemeleri
- **Ay sonu**: yukarıdakilere ek olarak gelecek ayın ödemeleri

**Gün, kullanıcı tercihidir** (`ReminderPreference`): herkes ikisini de ayın istediği gününde
alabilir ya da hiç almayabilir. Tercihi olmayan kullanıcı varsayılanları kullanır (1 ve 25), yani
sistem baştan herkese gönderir; kullanıcı isterse kapatır.

**Mükerrer gönderim, gün karşılaştırmasının tam eşitlik olmasıyla engellenir**; veritabanında
"gönderildi mi" kaydı tutulmaz. Kişinin seçtiği gün ayda bir kez geldiği için iş o kişi için ayda
bir kez koşar. Karşılaştırma aralığa çevrilirse bu güvence kaybolur ve kayıt tutmak zorunlu hâle
gelir. Gün seçenekleri 1-28 ile sınırlıdır (`ReminderPreference.MAX_DAY`): 29-31 seçilebilseydi o
gün olmayan aylarda hatırlatma hiç gitmezdi.

İki hatırlatma aynı güne denk gelirse **tek e-posta** gönderilir (gelecek ay dahil edilir); aynı
gün iki mail gitmez.

Akış bilerek iki evreye ayrılmıştır:

1. `collect_recipients()` — `db_session` içinde bütün veriyi toplar ve **entity içermeyen düz
   sözlüklere** çevirir.
2. Gönderim — veritabanı oturumu kapalıyken şablonu basıp SMTP'ye çıkar.

Böylece SMTP beklemeleri (`EmailBot` hata hâlinde 60 sn uyuyabilir) boyunca uzun bir veritabanı
işlemi açık kalmaz.
"""
import os
from datetime import date
from decimal import Decimal
from time import sleep

from pony.orm import db_session

from sandik.transaction import db as transaction_db
from sandik.transaction import utils as transaction_utils
from sandik.utils import period as period_utils
from sandik.utils.db_models import Contribution, ReminderPreference, WebUser
from sandik.utils.sorting import turkish_sort_key

KIND_MONTH_START = "month_start"
KIND_NEXT_MONTH = "next_month"

DEFAULT_SLEEP_SECONDS = 2


def is_enabled():
    """Acil kapatma valfi. Varsayılan açık."""
    return os.getenv("SANDIKv2_REMINDER_EMAIL_ENABLED", "1").strip().lower() not in ("0", "false", "hayir", "")


def get_test_address():
    """Tanımlıysa bütün e-postalar bu adrese gider ve konuya '[TEST]' eklenir."""
    return (os.getenv("SANDIKv2_REMINDER_EMAIL_TEST_ADDRESS") or "").strip() or None


def get_sleep_seconds():
    try:
        return float(os.getenv("SANDIKv2_REMINDER_EMAIL_SLEEP_SECONDS", DEFAULT_SLEEP_SECONDS))
    except ValueError:
        return DEFAULT_SLEEP_SECONDS


def reminder_for_today(web_user, today: date = None):
    """Bugün bu kişiye hangi hatırlatma gönderilecek?

    `None` → gönderilmez. `False` → yalnızca bu ayın ödemeleri. `True` → gelecek ay da dahil.

    Karşılaştırma **tam eşitliktir**; mükerrer engeli buna dayanır (bkz. modül açıklaması).
    İki tercih aynı güne denk gelirse gelecek ayı içeren tek e-posta gönderilir.
    """
    today = today or date.today()
    month_start_day, next_month_day = web_user.get_reminder_days()

    if next_month_day != ReminderPreference.OFF and today.day == next_month_day:
        return True
    if month_start_day != ReminderPreference.OFF and today.day == month_start_day:
        return False
    return None


def reminder_for_kind(web_user, kind):
    """Elle çalıştırma: günü yok sayar ama **kapatmış kullanıcıya yine göndermez**.

    `--hatirlatma-ay-basi` / `--hatirlatma-ay-sonu` bunu kullanır; tercihini kapatmış birine elle
    çalıştırmayla mail gitmesi istenmez.
    """
    month_start_day, next_month_day = web_user.get_reminder_days()
    if kind == KIND_NEXT_MONTH:
        return True if next_month_day != ReminderPreference.OFF else None
    return False if month_start_day != ReminderPreference.OFF else None


# --- Veri toplama -----------------------------------------------------------------------------

def _payment_row(payment, show_share):
    """Bir `Contribution`/`Installment` kaydını şablonun beklediği düz sözlüğe çevirir."""
    if isinstance(payment, Contribution):
        type_text = "Aidat"
    else:
        type_text = f"Taksit ({payment.get_installment_no()}/{payment.debt_ref.number_of_installment})"
    return {
        "term": payment.term,
        "term_text": period_utils.period_to_tr_text(payment.term),
        "type": type_text,
        "share": f"{payment.share_ref.share_order_of_member}. hisse" if show_share else None,
        "amount": payment.get_unpaid_amount(),
    }


def _next_month_contribution_rows(member, next_term, show_share):
    """Gelecek ayın aidat satırları.

    Aidat kayıtları yalnızca içinde bulunulan aya kadar oluşturulur
    (`transaction_utils.create_due_contributions_for_share`), dolayısıyla ayın 25'inde gelecek ayın
    `Contribution` satırları henüz yoktur. Tutar burada hesaplanır — `transaction_db`'deki
    `create_contribution`'ın varsayılanıyla (üyenin aidat tutarı, hisse başına) aynı formül, yani
    ayın 1'inde oluşacak kayıtla aynı sonucu verir. **Veritabanına hiçbir şey yazılmaz.**

    Kayıt zaten oluşturulmuşsa (ör. elle) o hisse için satır üretilmez; gerçek kayıt `get_payments`
    üzerinden zaten listeye girmiştir.
    """
    rows = []
    for share in member.get_active_shares().order_by(lambda s: s.share_order_of_member):
        if transaction_db.get_contribution(share_ref=share, term=next_term):
            continue
        rows.append({
            "term": next_term,
            "term_text": period_utils.period_to_tr_text(next_term),
            "type": "Aidat",
            "share": f"{share.share_order_of_member}. hisse" if show_share else None,
            "amount": member.contribution_amount,
        })
    return rows


def _sort_rows(rows):
    return sorted(rows, key=lambda r: (r["term"], r["type"], r["share"] or ""))


def collect_member_section(member, include_next_month, url_builder):
    """Tek bir sandık üyeliği için e-postadaki bölümü hazırlar. Ödeme yoksa `None` döner."""
    current_term = period_utils.current_period()
    next_term = period_utils.next_period()
    show_share = member.get_active_shares().count() > 1

    overdue, this_month = [], []
    for payment in transaction_utils.get_payments(whose=member, is_fully_paid=False, is_due=True):
        if payment.get_unpaid_amount() <= 0:
            continue
        (this_month if payment.term == current_term else overdue).append(_payment_row(payment, show_share))

    next_month = []
    if include_next_month:
        for payment in transaction_utils.get_payments(whose=member, is_fully_paid=False, periods=[next_term]):
            if payment.get_unpaid_amount() <= 0:
                continue
            next_month.append(_payment_row(payment, show_share))
        next_month += _next_month_contribution_rows(member=member, next_term=next_term, show_share=show_share)

    if not overdue and not this_month and not next_month:
        return None

    overdue = _sort_rows(overdue)
    this_month = _sort_rows(this_month)
    next_month = _sort_rows(next_month)

    overdue_total = sum((r["amount"] for r in overdue), Decimal(0))
    this_month_total = sum((r["amount"] for r in this_month), Decimal(0))
    next_month_total = sum((r["amount"] for r in next_month), Decimal(0))
    total = overdue_total + this_month_total + next_month_total
    # Üyenin yatırdığı ama henüz bir ödemeye dağıtılmamış parası; hatırlatılan tutardan düşülür.
    undistributed = member.total_of_undistributed_amount() or Decimal(0)

    sandik = member.sandik_ref
    bank_account = sandik.bank_accounts_set.filter(lambda ba: ba.is_primary).first()

    return {
        "sandik_id": sandik.id,
        "sandik_name": sandik.name,
        # Tutarlar şablonda `|money(...)` ile basılır; veri entity taşımadığı için birim kodu
        # burada düz sayı olarak gider.
        "currency": sandik.currency,
        "summary_url": url_builder(sandik.id),
        "iban": bank_account.get_iban_string() if bank_account else None,
        "iban_holder": (bank_account.holder or bank_account.title) if bank_account else None,
        "overdue": overdue,
        "this_month": this_month,
        "next_month": next_month,
        "overdue_total": overdue_total,
        "this_month_total": this_month_total,
        "next_month_total": next_month_total,
        "undistributed": undistributed,
        "total": total,
        "remaining": total - undistributed,
    }


def collect_reminder_data(web_user: WebUser, include_next_month: bool, url_builder,
                          preference_url_builder=None):
    """Bir kişinin bütün sandık üyeliklerini kapsayan e-posta verisi. Ödemesi yoksa `None` döner.

    Kişi başına tek e-posta gönderilir; birden fazla sandıktaki üyelikler tek mailde bölüm bölüm
    listelenir (`general/utils.py` içindeki `get_home_page_data` ile aynı yaklaşım).
    """
    members = sorted(
        web_user.members_set.filter(lambda m: m.is_active and m.sandik_ref.is_active)[:],
        key=lambda m: turkish_sort_key(m.sandik_ref.name)
    )

    sections = []
    for member in members:
        section = collect_member_section(member=member, include_next_month=include_next_month,
                                         url_builder=url_builder)
        if section:
            sections.append(section)

    if not sections:
        return None

    current_term = period_utils.current_period()
    next_term = period_utils.next_period()
    return {
        "web_user_id": web_user.id,
        "email_address": web_user.email_address,
        "name_surname": web_user.name_surname,
        # E-postanın altındaki "bu e-postaları almak istemiyorum" bağlantısı. Adres üretimi
        # dışarıdan enjekte edilir (jeton üretmek uygulama bağlamı ister); testlerde None kalır.
        "preference_url": preference_url_builder(web_user) if preference_url_builder else None,
        "sandiks": sections,
        "grand_total": sum((s["total"] for s in sections), Decimal(0)),
        "grand_remaining": sum((s["remaining"] for s in sections), Decimal(0)),
        # Sandıklar farklı para birimlerindeyse genel toplam anlamsızdır; şablon onu göstermez.
        "is_single_currency": len({s["currency"] for s in sections}) <= 1,
        "currency": sections[0]["currency"] if sections else None,
        "current_term": current_term,
        "next_term": next_term,
        "current_term_text": period_utils.period_to_tr_text(current_term),
        "next_term_text": period_utils.period_to_tr_text(next_term),
        "include_next_month": include_next_month,
    }


def build_subject(data):
    if data["include_next_month"]:
        return f"{data['current_term_text']} ve {data['next_term_text']} ödemeleriniz"
    return f"{data['current_term_text']} ödemeleriniz"


def collect_recipients(url_builder, today: date = None, kind=None, preference_url_builder=None):
    """Mail gönderilecek kişilerin verisini toplar. `db_session` içinde çağrılmalıdır.

    `kind` verilmezse **gecelik kip**: herkesin kendi tercih ettiği güne bakılır. `kind` verilirse
    **elle kip**: gün yok sayılır, yalnızca o hatırlatmayı kapatmış olanlar atlanır.

    Ödemesi olmayan kişi listeye girmez (`collect_reminder_data` `None` döner).
    """
    recipients = []
    for web_user in WebUser.select().order_by(WebUser.id):
        if not web_user.email_address:
            continue

        if kind:
            include_next_month = reminder_for_kind(web_user=web_user, kind=kind)
        else:
            include_next_month = reminder_for_today(web_user=web_user, today=today)
        if include_next_month is None:
            continue

        data = collect_reminder_data(web_user=web_user, include_next_month=include_next_month,
                                     url_builder=url_builder,
                                     preference_url_builder=preference_url_builder)
        if data:
            recipients.append(data)
    return recipients


# --- İş yürütme -------------------------------------------------------------------------------

def run_payment_reminder(url_builder, render, send, today: date = None, kind=None, dry_run=False,
                         log=print, preference_url_builder=None):
    """Hatırlatma gönderimini baştan sona çalıştırır.

    Mükerrer kontrolü burada değil, `reminder_for_today()` içindeki tam gün eşitliğindedir: bu
    fonksiyon her çağrıldığında, seçilen kişilere gönderir. Elle çağırırken bu bilinerek çağrılır.

    `render(data) -> html` ve `send(to_address, subject, html) -> None` dışarıdan verilir; böylece
    testler Flask ve SMTP olmadan çalışabilir.

    Döner: `{"sent": int, "failed": int, "recipients": int}`
    """
    result = {"sent": 0, "failed": 0, "recipients": 0}
    label = f"[{kind}] " if kind else ""

    # Toplama db_session içinde biter; gönderim sırasında veritabanı oturumu açık kalmaz.
    with db_session:
        recipients = collect_recipients(url_builder=url_builder, today=today, kind=kind,
                                        preference_url_builder=preference_url_builder)

    result["recipients"] = len(recipients)
    log(f"{label}{len(recipients)} kişiye gönderilecek")

    test_address = get_test_address()
    sleep_seconds = get_sleep_seconds()

    for index, data in enumerate(recipients):
        subject = build_subject(data)
        if test_address:
            subject = f"[TEST] {subject}"
        html = render(data)

        if dry_run:
            log(f"  - (kuru) {data['email_address']} <- {subject}")
            continue

        to_address = test_address or data["email_address"]
        try:
            send(to_address, subject, html)
        except Exception as e:
            result["failed"] += 1
            log(f"  ! {to_address} gönderilemedi: {type(e).__name__} -> {e}")
        else:
            result["sent"] += 1
            log(f"  - {to_address} gönderildi")

        if sleep_seconds and index < len(recipients) - 1:
            sleep(sleep_seconds)

    log(f"{label}bitti: {result['sent']} gönderildi, {result['failed']} başarısız")
    return result
