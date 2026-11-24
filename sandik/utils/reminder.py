"""Üyelere aylık ödeme hatırlatma e-postası gönderen iş.

`clock.py` her gece çalışır. Bu modül "bugün kime hatırlatma gönderilmeli" sorusunu cevaplar ve
gönderimi yürütür. **Tek bir hatırlatma vardır, kişi ayda iki gününü seçer** ("1. hatırlatma",
"2. hatırlatma"); e-posta geçmiş aylardan kalan + bu ayın ödenmemiş ödemelerini listeler.

Eskiden "ay başı" (bu ay) ve "ay sonu" (bu ay + gelecek ay) diye iki ayrı hatırlatma vardı. Kullanıcı
istedi (2026-11): gelecek ay kaldırıldı (bu ayı ödemiş üyeye gelecek ayın aidatı "ödemeniz gereken" diye
gidiyor, kafa karıştırıyordu), ikisi aynı olunca da tek hatırlatmaya indirildi. Tercih anahtarlarının adları
(`reminder_month_start_day`, `reminder_next_month_day`) kayıtlı veriyle uyumlu kalsın diye değişmedi;
yalnızca 1. ve 2. günü tutarlar.

**Günler kullanıcı tercihidir** (`ReminderPreference`): herkes ikisini de ayın istediği gününe alabilir ya
da kapatabilir. Tercihi olmayan kullanıcı varsayılanları kullanır (1 ve 25), yani
sistem baştan herkese gönderir; kullanıcı isterse kapatır.

**Mükerrer gönderim, gün karşılaştırmasının tam eşitlik olmasıyla engellenir**; veritabanında
"gönderildi mi" kaydı tutulmaz. Kişinin seçtiği gün ayda bir kez geldiği için iş o kişi için ayda
bir kez koşar. Karşılaştırma aralığa çevrilirse bu güvence kaybolur ve kayıt tutmak zorunlu hâle
gelir. Gün seçenekleri 1-28 ile sınırlıdır (`ReminderPreference.MAX_DAY`): 29-31 seçilebilseydi o
gün olmayan aylarda hatırlatma hiç gitmezdi.

İki gün aynıysa **tek e-posta** gönderilir; aynı gün iki mail gitmez.

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

from sandik.transaction import utils as transaction_utils
from sandik.utils import period as period_utils
from sandik.utils.db_models import Contribution, ReminderPreference, WebUser
from sandik.utils.sorting import turkish_sort_key

DEFAULT_SLEEP_SECONDS = 2

# Satır türleri. E-postada ödemeler tek tek değil, sandık başına bu iki kalemde toplanır.
KIND_CONTRIBUTION = "contribution"
KIND_INSTALLMENT = "installment"


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


def is_reminder_day(web_user, today: date = None) -> bool:
    """Bugün bu kişinin seçtiği hatırlatma günlerinden biri mi?

    Karşılaştırma **tam eşitliktir**; mükerrer engeli buna dayanır (bkz. modül açıklaması).
    İki gün aynıysa tek e-posta gönderilir.
    """
    today = today or date.today()
    return any(day != ReminderPreference.OFF and today.day == day for day in web_user.get_reminder_days())


def wants_reminder(web_user) -> bool:
    """Elle çalıştırma (`--hatirlatma`): günü yok sayar ama **iki günü de kapatmış kullanıcıya göndermez**."""
    return any(day != ReminderPreference.OFF for day in web_user.get_reminder_days())


# --- Veri toplama -----------------------------------------------------------------------------

def _payment_row(payment, show_share):
    """Bir `Contribution`/`Installment` kaydını şablonun beklediği düz sözlüğe çevirir."""
    if isinstance(payment, Contribution):
        kind, type_text = KIND_CONTRIBUTION, "Aidat"
    else:
        kind = KIND_INSTALLMENT
        type_text = f"Taksit ({payment.get_installment_no()}/{payment.debt_ref.number_of_installment})"
    return {
        "kind": kind,
        "term": payment.term,
        "term_text": period_utils.period_to_tr_text(payment.term),
        "type": type_text,
        "share": f"{payment.share_ref.share_order_of_member}. hisse" if show_share else None,
        "amount": payment.get_unpaid_amount(),
    }


def _projected_contribution_rows(member, term, show_share):
    """Henüz oluşturulmamış bir ayın aidat satırları.

    Aidat kayıtları yalnızca içinde bulunulan aya kadar oluşturulur
    (`transaction_utils.create_due_contributions_for_share`); yönetici ön hatırlatması ayın son günü
    yarınki (yeni ayın) e-postasını hesaplarken o ayın `Contribution` satırları henüz yoktur. Tutar burada hesaplanır — `transaction_db`'deki
    `create_contribution`'ın varsayılanıyla (üyenin aidat tutarı, hisse başına) aynı formül, yani
    ayın 1'inde oluşacak kayıtla aynı sonucu verir. **Veritabanına hiçbir şey yazılmaz.**

    Kayıt zaten oluşturulmuşsa (ör. elle) o hisse için satır üretilmez; gerçek kayıt `get_payments`
    üzerinden zaten listeye girmiştir.
    """
    rows = []
    for share in member.get_active_shares().order_by(lambda s: s.share_order_of_member):
        # `get` değil `exists`: canlı veride aynı hisse/ay için birden fazla aidat olabiliyor (get hata verirdi).
        if Contribution.exists(share_ref=share, term=term):
            continue
        rows.append({
            "kind": KIND_CONTRIBUTION,
            "term": term,
            "term_text": period_utils.period_to_tr_text(term),
            "type": "Aidat",
            "share": f"{share.share_order_of_member}. hisse" if show_share else None,
            "amount": member.contribution_amount,
        })
    return rows


def _sort_rows(rows):
    return sorted(rows, key=lambda r: (r["term"], r["type"], r["share"] or ""))


def _sum_amounts(rows, kind=None):
    return sum((r["amount"] for r in rows if kind is None or r["kind"] == kind), Decimal(0))


def _term_group(label, rows):
    """E-postadaki bir dönem bloğu: dönemin adı ve o dönemin aidat/taksit toplamları."""
    return {
        "label": label,
        "contribution_total": _sum_amounts(rows, KIND_CONTRIBUTION),
        "installment_total": _sum_amounts(rows, KIND_INSTALLMENT),
        "total": _sum_amounts(rows),
    }


def _unpaid_rows(member, show_share, **filters):
    rows = []
    for payment in transaction_utils.get_payments(whose=member, is_fully_paid=False, **filters):
        if payment.get_unpaid_amount() <= 0:
            continue
        rows.append(_payment_row(payment, show_share))
    return rows


def collect_member_section(member, url_builder, current_term=None):
    """Tek bir sandık üyeliği için e-postadaki bölümü hazırlar. Ödeme yoksa `None` döner.

    Satırlar (`overdue`/`this_month`) tek tek hesaplanır ama **e-postada listelenmez**: şablon
    dönem başına (`terms`: geçmiş aylardan kalan, bu ay) iki kalemi
    (aidat, taksit) gösterir, ayrıntı için sitedeki "Ödemelerim" sayfasına bağlantı verir
    (`payments_url`). Satırlar toplamların kaynağı olarak ve testler için tutulur.

    `current_term`: e-postanın "bu ay"ı; verilmezse içinde bulunulan ay. Yönetici ön hatırlatması
    (`manager_reminder.py`) **yarın** gidecek e-postayı bugünden hesapladığı için ayın son günü
    gelecek ayı verir: o ayın aidatları henüz oluşturulmamıştır (gece oluşturulacak), bu yüzden
    burada hesaplanır (`_projected_contribution_rows`), yarınki e-postayla aynı sonuç çıkar.
    """
    real_current_term = period_utils.current_period()
    current_term = current_term or real_current_term
    show_share = member.get_active_shares().count() > 1

    overdue, this_month = [], []
    for row in _unpaid_rows(member, show_share, is_due=True):
        (this_month if row["term"] == current_term else overdue).append(row)
    if current_term > real_current_term:
        # "Bu ay" henüz gelmedi: o ayın taksitleri zaten kayıtlıdır, aidatları hesaplanır.
        this_month += _unpaid_rows(member, show_share, periods=[current_term])
        this_month += _projected_contribution_rows(member=member, term=current_term, show_share=show_share)

    if not overdue and not this_month:
        return None

    overdue = _sort_rows(overdue)
    this_month = _sort_rows(this_month)

    overdue_total = _sum_amounts(overdue)
    this_month_total = _sum_amounts(this_month)
    total = overdue_total + this_month_total
    all_rows = overdue + this_month
    # Üyenin yatırdığı ama henüz bir ödemeye dağıtılmamış parası; hatırlatılan tutardan düşülür.
    undistributed = member.total_of_undistributed_amount() or Decimal(0)

    # E-postada tutarlar dönem dönem gösterilir: hangi tutarın hangi aya ait olduğu anlaşılsın
    # (kullanıcı istedi). "Bu ay" hiç ödemesi olmasa da listelenir, şablon onu "ödenmemiş ödemeniz yok"
    # diye yazar; geçmiş aylardan kalan yalnızca varsa görünür.
    terms = []
    if overdue:
        terms.append(_term_group("Geçmiş aylardan kalan", overdue))
    terms.append(_term_group(period_utils.period_to_tr_text(current_term), this_month))

    sandik = member.sandik_ref
    bank_account = sandik.bank_accounts_set.filter(lambda ba: ba.is_primary).first()

    return {
        "sandik_id": sandik.id,
        "sandik_name": sandik.name,
        # Tutarlar şablonda `|money(...)` ile basılır; veri entity taşımadığı için birim kodu
        # burada düz sayı olarak gider.
        "currency": sandik.currency,
        # Sitedeki "Ödemelerim" sayfası; e-postada ödemeler tek tek listelenmediği için ayrıntı orada.
        "payments_url": url_builder(sandik.id),
        "iban": bank_account.get_iban_string() if bank_account else None,
        "iban_holder": (bank_account.holder or bank_account.title) if bank_account else None,
        "overdue": overdue,
        "this_month": this_month,
        "overdue_total": overdue_total,
        "this_month_total": this_month_total,
        "terms": terms,
        "contribution_total": _sum_amounts(all_rows, KIND_CONTRIBUTION),
        "installment_total": _sum_amounts(all_rows, KIND_INSTALLMENT),
        "undistributed": undistributed,
        "total": total,
        "remaining": total - undistributed,
    }


def collect_reminder_data(web_user: WebUser, url_builder, preference_url_builder=None):
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
        section = collect_member_section(member=member, url_builder=url_builder)
        if section:
            sections.append(section)

    if not sections:
        return None

    current_term = period_utils.current_period()
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
        "current_term_text": period_utils.period_to_tr_text(current_term),
    }


def build_subject(data):
    return f"{data['current_term_text']} ödemeleriniz"


def collect_recipients(url_builder, today: date = None, manual=False, preference_url_builder=None):
    """Mail gönderilecek kişilerin verisini toplar. `db_session` içinde çağrılmalıdır.

    **Gecelik kip** (varsayılan): herkesin kendi tercih ettiği günlere bakılır. `manual=True` **elle
    kip**: gün yok sayılır, yalnızca hatırlatmayı tamamen kapatmış olanlar atlanır.

    Ödemesi olmayan kişi listeye girmez (`collect_reminder_data` `None` döner).
    """
    recipients = []
    for web_user in WebUser.select().order_by(WebUser.id):
        if not web_user.email_address:
            continue

        if not (wants_reminder(web_user) if manual else is_reminder_day(web_user=web_user, today=today)):
            continue

        data = collect_reminder_data(web_user=web_user, url_builder=url_builder,
                                     preference_url_builder=preference_url_builder)
        if data:
            recipients.append(data)
    return recipients


# --- İş yürütme -------------------------------------------------------------------------------

def run_payment_reminder(url_builder, render, send, today: date = None, manual=False, dry_run=False,
                         log=print, preference_url_builder=None):
    """Hatırlatma gönderimini baştan sona çalıştırır.

    Mükerrer kontrolü burada değil, `is_reminder_day()` içindeki tam gün eşitliğindedir: bu
    fonksiyon her çağrıldığında, seçilen kişilere gönderir. Elle çağırırken bu bilinerek çağrılır.

    `render(data) -> html` ve `send(to_address, subject, html) -> None` dışarıdan verilir; böylece
    testler Flask ve SMTP olmadan çalışabilir.

    Döner: `{"sent": int, "failed": int, "recipients": int}`
    """
    result = {"sent": 0, "failed": 0, "recipients": 0}
    label = "[elle] " if manual else ""

    # Toplama db_session içinde biter; gönderim sırasında veritabanı oturumu açık kalmaz.
    with db_session:
        recipients = collect_recipients(url_builder=url_builder, today=today, manual=manual,
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
