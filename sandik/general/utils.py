from datetime import date, timedelta
from decimal import Decimal

from sandik.general import db
from sandik.general.exceptions import BankAccountNotFound, PrimaryBankAccountCannotBeDeleted, \
    UnauthorizedBankAccountOperation
from sandik.transaction import db as transaction_db
from sandik.transaction import utils as transaction_utils
from sandik.utils import period as period_utils
from sandik.utils.sorting import turkish_sort_key


def get_home_page_data(web_user):
    """
    Ana sayfada, kullanıcının üye olduğu bütün sandıkları kapsayan iki tablo için veri hazırlar:
        - status_rows: Her sandıktaki son durum (ödenen aidat, alınan borç, ödenen taksit, ay sonu, mil sonu...)
          ve status_totals: bu tablonun sütun toplamları
        - payment_rows: Ödenmemiş ödemelerin ay bazında, sandık sandık dağılımı
    Yetki verilmiş fakat üye olunmayan sandıklar bu tablolara dahil edilmez.
    """
    members = sorted(
        web_user.members_set.filter(lambda m: m.is_active)[:],
        key=lambda m: turkish_sort_key(m.sandik_ref.name)
    )

    # --- Tablo 1: Sandık bazında son durum ---
    status_rows = []
    undistributed_amounts = {}  # member.id -> işleme konmamış (henüz bir ödemeye dağıtılmamış) tutar
    for member in members:
        undistributed = member.total_of_undistributed_amount() or Decimal(0)
        undistributed_amounts[member.id] = undistributed
        sum_of_unpaid_and_due = transaction_utils.sum_of_unpaid_and_due_payments(whose=member) or Decimal(0)
        sum_of_future_and_unpaid = transaction_utils.sum_of_future_and_unpaid_payments(whose=member) or Decimal(0)
        status_rows.append({
            "member": member,
            "sandik": member.sandik_ref,
            "paid_contributions": member.sum_of_paid_contributions() or Decimal(0),
            "total_debts": member.sum_of_debts() or Decimal(0),
            "paid_installments": member.sum_of_paid_installments() or Decimal(0),
            "unpaid_debt": member.sum_of_unpaid_amount_of_debts() or Decimal(0),
            "undistributed": undistributed,
            "month_end": undistributed - sum_of_unpaid_and_due,
            "mile_end": undistributed - sum_of_unpaid_and_due - sum_of_future_and_unpaid,
        })

    # Sandıklar farklı para birimlerinde olabilir; farklı birimdeki tutarlar toplanamayacağı için
    # toplam satırı birim başına bir kez üretilir. Kullanıcının bütün sandıkları aynı birimdeyse
    # (bugün olağan durum) tek satır çıkar ve tablo eskisi gibi görünür.
    status_total_columns = ["paid_contributions", "total_debts", "paid_installments", "unpaid_debt",
                            "undistributed", "month_end", "mile_end"]
    status_totals_by_currency = []
    for currency in sorted({row["sandik"].currency for row in status_rows}):
        rows_of_currency = [row for row in status_rows if row["sandik"].currency == currency]
        totals = {
            column: sum((row[column] for row in rows_of_currency), Decimal(0))
            for column in status_total_columns
        }
        # Temsilci sandık yalnızca biçimlendirme (`|money`) içindir; aynı birimdeki bütün
        # sandıklar aynı sonucu verir.
        totals["sandik"] = rows_of_currency[0]["sandik"]
        status_totals_by_currency.append(totals)

    # --- Tablo 2: Aylık ödemeler (ödenmemiş aidat + taksitler) ---
    # payments_matrix[term][member.id] = o ay o sandıkta ödenmemiş toplam miktar
    payments_matrix = {}
    for member in members:
        for payment in transaction_utils.get_payments(whose=member, is_fully_paid=False):
            unpaid_amount = payment.get_unpaid_amount()
            if unpaid_amount <= 0:
                continue
            row = payments_matrix.setdefault(payment.term, {})
            row[member.id] = row.get(member.id, Decimal(0)) + unpaid_amount

    # İşleme konmamış para: üyenin yatırdığı ama henüz bir aidat/taksite dağıtılmamış tutarı.
    # Ödenmemiş ödemeleri karşılamak için kullanılabileceğinden "Toplam" satırında bu tutar
    # düşülerek gerçekte kalan net borç gösterilir; sadece varsa (>0) ayrıca bir satır olarak da
    # gösterilir ki kullanıcı bu tutarın nereden geldiğini görebilsin.
    undistributed_cells = {member.id: undistributed_amounts[member.id]
                           for member in members if undistributed_amounts[member.id] > 0}
    undistributed_row = {
        "cells": undistributed_cells,
        "total": sum(undistributed_cells.values(), Decimal(0)),
    } if undistributed_cells else None

    payments_table = _build_payments_table(members=members, payments_matrix=payments_matrix,
                                           undistributed_amounts=undistributed_amounts)

    # Tablonun "gelecek ayların aidatları da" seçeneği: aidat kayıtları yalnızca içinde bulunulan
    # aya kadar oluşturulduğu için gelecek aylarda tabloda yalnızca taksitler görünür. Bu ikinci
    # tablo o ayların aidatlarını hesaplayıp ekler; iki tablo da basılır, hangisinin görüneceğini
    # tarayıcıdaki seçim belirler.
    last_term = max([period_utils.next_period()] + list(payments_matrix.keys()))
    future_periods = period_utils.get_periods_between_two_period(first_period=period_utils.next_period(),
                                                                 last_period=last_term)
    matrix_with_contributions = {term: dict(cells) for term, cells in payments_matrix.items()}
    projected_cells = {}  # term -> {member.id, ...}: hesaplanan aidat içeren hücreler
    for member in members:
        for term, amount in _future_contribution_amounts(member=member, periods=future_periods).items():
            row = matrix_with_contributions.setdefault(term, {})
            row[member.id] = row.get(member.id, Decimal(0)) + amount
            projected_cells.setdefault(term, set()).add(member.id)
    payments_table_with_contributions = _build_payments_table(
        members=members, payments_matrix=matrix_with_contributions,
        undistributed_amounts=undistributed_amounts, projected_cells=projected_cells,
    )

    # Aylık ödemeler tablosunda satır/sütun toplamları sandıklar arasıdır; birden fazla para
    # birimi varsa bu toplamlar anlamsızdır ve şablon onları göstermez.
    currencies = {member.sandik_ref.currency for member in members}
    is_single_currency = len(currencies) <= 1

    return {
        "members": members,
        "status_rows": status_rows,
        "status_totals_by_currency": status_totals_by_currency,
        "is_single_currency": is_single_currency,
        # Tek birim varken toplamların hangi birimde gösterileceği
        "currency_sandik": members[0].sandik_ref if is_single_currency and members else None,
        **payments_table,
        "payments_table_with_contributions": payments_table_with_contributions,
        "undistributed_row": undistributed_row,
        "current_period": period_utils.current_period(),
    }


def _build_payments_table(members, payments_matrix, undistributed_amounts, projected_cells=None):
    """Aylık ödemeler tablosunun satırlarını ve (işleme konmamış para düşülmüş) toplamlarını üretir.
    `projected_cells`: hesaplanan (henüz oluşturulmamış) aidat içeren hücreler, `term -> {member.id}`."""
    projected_cells = projected_cells or {}
    payment_rows = []
    for term in sorted(payments_matrix.keys()):
        cells = payments_matrix[term]
        payment_rows.append({
            "term": term,
            "cells": cells,
            "total": sum(cells.values()),
            "projected_member_ids": projected_cells.get(term, set()),
        })

    net_sandik_totals = {
        member.id: sum((row["cells"].get(member.id, Decimal(0)) for row in payment_rows), Decimal(0))
        - undistributed_amounts[member.id]
        for member in members
    }
    return {
        "payment_rows": payment_rows,
        "sandik_totals": net_sandik_totals,
        "grand_total": sum(net_sandik_totals.values()) if net_sandik_totals else Decimal(0),
    }


def _future_contribution_amounts(member, periods):
    """Henüz oluşturulmamış aidatların ay bazında toplamı: `{term: tutar}`.

    Aidat kayıtları yalnızca içinde bulunulan aya kadar oluşturulur
    (`transaction_utils.create_due_contributions_for_share`). Tutar, kaydı oluşturacak
    `transaction_db.create_contribution`ın varsayılanıyla aynı formüldür (üyenin aidat tutarı, hisse
    başına); hatırlatma e-postasındaki gelecek ay aidatıyla da aynıdır (`reminder.py`). Kaydı zaten
    olan (ör. elle oluşturulmuş) hisse/ay atlanır: ödenmemişse gerçek kayıt tabloya zaten girmiştir.
    **Veritabanına hiçbir şey yazılmaz.**
    """
    if not periods or member.contribution_amount <= 0:
        return {}
    first_period = periods[0]
    existing = {(c.share_ref.id, c.term) for c in transaction_db.select_contributions(
        lambda c: c.share_ref.member_ref == member and c.term >= first_period)}
    amounts = {}
    for share in member.get_active_shares():
        opening_period = period_utils.date_to_period(share.date_of_opening)
        for term in periods:
            if term < opening_period or (share.id, term) in existing:
                continue
            amounts[term] = amounts.get(term, Decimal(0)) + member.contribution_amount
    return amounts


# --- Mil sonu geçmişi (/mil-sonu-gecmisi) ---------------------------------------------------------
# Ana sayfadaki "Mil sonu" sütununun (status_rows -> mile_end) geçmişteki her dilim sonundaki değeri.
# Geçmiş durum veritabanında saklanmaz, bugünkü kayıtlardan geriye doğru hesaplanır. Ayrıntı:
# CLAUDE.md -> "Mil sonu geçmişi".

HISTORY_SLICES = {  # adresteki değer -> etiket
    "gun": "Günlük",
    "hafta": "Haftalık",
    "ay": "Aylık",
    "3ay": "3 aylık",
    "6ay": "6 aylık",
    "yil": "Yıllık",
}
DEFAULT_HISTORY_SLICE = "ay"
# Bu dilimlerde tabloda yalnızca mil sonunun değiştiği satırlar listelenir (5 yıl günlük 1800 satır eder).
HISTORY_SLICES_LISTING_ONLY_CHANGES = {"gun", "hafta"}

HISTORY_RANGES = {  # adresteki değer -> (etiket, kaç ay; None = ilk kayıttan bugüne)
    "12ay": ("Son 12 ay", 12),
    "3yil": ("Son 3 yıl", 36),
    "tumu": ("Tümü", None),
}
DEFAULT_HISTORY_RANGE = "12ay"

# Seçimi taşıyan adres parametreleri; sayfa bunlardan biri olmadan açılırsa son seçim kullanılır.
HISTORY_ARG_NAMES = ("aralik", "baslangic", "bitis", "dilim")


def parse_history_selection(args):
    """Adres parametrelerinden (ya da kaydedilmiş seçimden) aralık ve dilim seçimini okur.

    Hazır bir aralık (`aralik=12ay`) ay olarak değil adıyla saklanır: "Son 12 ay" seçilip kaydedilen
    bir seçim gelecek ay da son 12 ayı göstermelidir. Geçersiz değerler sessizce varsayılana düşer.
    """
    history_slice = args.get("dilim")
    if history_slice not in HISTORY_SLICES:
        history_slice = DEFAULT_HISTORY_SLICE

    start_period, end_period = args.get("baslangic"), args.get("bitis")
    if period_utils.is_valid_period(start_period) and period_utils.is_valid_period(end_period):
        if start_period > end_period:
            start_period, end_period = end_period, start_period
        return {"slice": history_slice, "range": None, "start_period": start_period, "end_period": end_period,
                "args": {"baslangic": start_period, "bitis": end_period, "dilim": history_slice}}

    history_range = args.get("aralik")
    if history_range not in HISTORY_RANGES:
        history_range = DEFAULT_HISTORY_RANGE
    return {"slice": history_slice, "range": history_range, "start_period": None, "end_period": None,
            "args": {"aralik": history_range, "dilim": history_slice}}


def _last_day_of_month(day):
    return (day.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


def history_point_dates(start_date, end_date, history_slice):
    """Aralıktaki dilim sonları (artan sırada). Aralığın son günü dilim sonu değilse o da eklenir:
    bitmemiş bir dilimin (ör. bu ayın) değeri bugünün değeridir."""
    if start_date > end_date:
        return []

    if history_slice in ("gun", "hafta"):
        points = []
        day = start_date
        while day <= end_date:
            if history_slice == "gun" or day.weekday() == 6:  # hafta pazar günü biter
                points.append(day)
            day += timedelta(days=1)
    else:
        month_step = {"ay": 1, "3ay": 3, "6ay": 6, "yil": 12}[history_slice]
        points = []
        month_end = _last_day_of_month(start_date)
        while month_end <= end_date:
            # Dilimler takvime oturur: 3 aylık dilim mart/haziran/eylül/aralık sonunda biter.
            if month_end.month % month_step == 0:
                points.append(month_end)
            month_end = _last_day_of_month(month_end + timedelta(days=1))

    if not points or points[-1] != end_date:
        points.append(end_date)
    return points


def _mile_end_events(member_ids, today):
    """Mil sonunu değiştiren olaylar: `{member_id: [(tarih, değişim), ...]}`.

    Bugünkü mil sonu = işleme konmamış para - vadesi gelmiş ödenmemiş aidatlar - ödenmemiş bütün
    taksitler (`get_home_page_data` -> `mile_end`). Bir ödeme (para aidata/taksite işlenince) iki
    tarafı birden aynı tutarda azaltır, mil sonunu değiştirmez; geriye mil sonunu değiştiren dört
    olay kalır:
        + para girişi                    (para işleminin tarihinde)
        - işleme konmamış paranın iadesi (iadenin yapıldığı para çıkışının tarihinde)
        - aidatın vadesinin gelmesi      (dönemin ilk günü; gelecek dönemler bugün sayılmadığı için hiç)
        - borç alınması: bütün taksitleri (borcun verildiği para çıkışının tarihinde)
    Tek istisna, henüz sayılmayan bir aidata/taksite önceden yapılan ödemedir (ör. gelecek ayın
    aidatı): para, aidat sayılmaya başlayana kadar yalnızca işleme konmamış paradan düşer. Ödemenin
    tarihi, para işleminin tarihi ile ödemenin kaydedildiği andan hangisi geçse odur.

    Gelecek tarihli kayıtlar bugüne çekilir: bugünkü mil sonu onları zaten sayıyor.
    """
    current_period = period_utils.date_to_period(today)
    events = {member_id: [] for member_id in member_ids}

    def add(member_id, day, delta):
        events[member_id].append((min(day, today), delta))

    def add_payment(member_id, money_transaction_date, creation_time, amount, counted_from):
        """`counted_from`: ödenen kalemin mil sonunda sayılmaya başladığı gün (None: bugüne kadar hiç)."""
        paid_on = min(max(money_transaction_date, creation_time.date()), today)
        if counted_from is None or paid_on < counted_from:
            add(member_id, paid_on, -amount)
            if counted_from is not None:
                add(member_id, counted_from, amount)

    for _, member_id, day, amount in db.select_revenue_money_transaction_rows(member_ids):
        add(member_id, day, amount)
    for _, member_id, day, amount in db.select_retracted_rows(member_ids):
        add(member_id, day, -amount)
    for _, member_id, term, amount in db.select_contribution_rows(member_ids):
        if term <= current_period:
            add(member_id, period_utils.period_to_date(term), -amount)
    for _, member_id, debt_date, amount in db.select_installment_rows(member_ids):
        add(member_id, debt_date, -amount)
    for _, member_id, term, mt_date, creation_time, amount in db.select_contribution_payment_rows(member_ids):
        counted_from = period_utils.period_to_date(term) if term <= current_period else None
        add_payment(member_id, mt_date, creation_time, amount, counted_from)
    for _, member_id, debt_date, mt_date, creation_time, amount in db.select_installment_payment_rows(member_ids):
        add_payment(member_id, mt_date, creation_time, amount, min(debt_date, today))

    for member_events in events.values():
        member_events.sort(key=lambda event: event[0])
    return events


def _values_at(member_events, points):
    """Her dilim sonundaki birikmiş değer (olaylar ve noktalar artan sırada, tek geçiş)."""
    values = []
    total = Decimal(0)
    index = 0
    for point in points:
        while index < len(member_events) and member_events[index][0] <= point:
            total += member_events[index][1]
            index += 1
        values.append(total)
    return values


def get_mile_end_history(web_user, selection, today=None):
    """Kullanıcının hâlâ üyesi olduğu sandıklardaki mil sonunun dilim dilim değeri.

    Sandıklar para birimine göre gruplanır (farklı birimler toplanamaz); her grubun bir toplam
    serisi ve sandık sandık serileri vardır. Bugünle biten noktanın değeri ana sayfadaki mil sonuyla
    aynıdır (`tests/test_mile_end_history.py`).
    """
    today = today or date.today()
    members = sorted(
        web_user.members_set.filter(lambda m: m.is_active)[:],
        key=lambda m: turkish_sort_key(m.sandik_ref.name)
    )
    member_ids = [member.id for member in members]
    events = _mile_end_events(member_ids=member_ids, today=today) if members else {}

    if selection["range"] is None:
        start_date = period_utils.period_to_date(selection["start_period"])
        end_date = min(_last_day_of_month(period_utils.period_to_date(selection["end_period"])), today)
    else:
        month_count = HISTORY_RANGES[selection["range"]][1]
        if month_count is None:
            first_days = [member.date_of_membership for member in members]
            first_days += [member_events[0][0] for member_events in events.values() if member_events]
            start_date = min(first_days).replace(day=1) if first_days else today.replace(day=1)
        else:
            start_date = period_utils.period_to_date(
                period_utils.get_period_by_difference(period_utils.date_to_period(today), -(month_count - 1)))
        end_date = today

    points = history_point_dates(start_date=start_date, end_date=end_date, history_slice=selection["slice"])
    values = {member_id: _values_at(events[member_id], points) for member_id in member_ids}

    groups = []
    for currency in sorted({member.sandik_ref.currency for member in members}):
        group_members = [member for member in members if member.sandik_ref.currency == currency]
        groups.append({
            # Temsilci sandık yalnızca biçimlendirme (`|money`) içindir.
            "sandik": group_members[0].sandik_ref,
            "members": group_members,
            "total": [sum((values[member.id][i] for member in group_members), Decimal(0))
                      for i in range(len(points))],
        })

    # Tablo satırları en yeniden eskiye; günlük/haftalık dilimde yalnızca değişen satırlar. Aralığın
    # ilk ve son noktası (çoğunlukla bugün) değişmemiş olsa da listelenir.
    row_indexes = []
    for i in range(len(points)):
        if (selection["slice"] in HISTORY_SLICES_LISTING_ONLY_CHANGES and 0 < i < len(points) - 1
                and all(values[member_id][i] == values[member_id][i - 1] for member_id in member_ids)):
            continue
        row_indexes.append(i)
    row_indexes.reverse()

    labels = [point.strftime("%d.%m.%Y") for point in points]
    # Grafiğe giden veri: tutarlar metin olarak (Decimal; JS parseFloat ile okur, bkz. CLAUDE.md).
    chart = {
        "labels": labels,
        "groups": [{
            "currency": {"symbol": group["sandik"].currency_symbol(), "places": group["sandik"].currency_places()},
            "total_label": "Toplam" if len(group["members"]) > 1 else group["members"][0].sandik_ref.name,
            "total": [str(value) for value in group["total"]],
            "series": [{"name": member.sandik_ref.name, "values": [str(value) for value in values[member.id]]}
                       for member in group["members"]] if len(group["members"]) > 1 else [],
        } for group in groups],
    }

    return {
        "members": members,
        "points": points,
        "labels": labels,
        "chart": chart,
        # Sandık sandık gösterimin anlamı ancak bir toplamın birden fazla sandıktan oluştuğunda var.
        "has_per_sandik": any(len(group["members"]) > 1 for group in groups),
        "today": today,
        "start_date": start_date,
        "end_date": end_date,
        "member_values": values,
        "groups": groups,
        "row_indexes": row_indexes,
        "lists_only_changes": selection["slice"] in HISTORY_SLICES_LISTING_ONLY_CHANGES,
    }


def remove_bank_account(bank_account_id, deleted_by):
    bank_account = db.get_bank_account(id=bank_account_id)
    if not bank_account:
        raise BankAccountNotFound("Banka hesabı bulunamadı.", create_log=True)

    # Silme yetkisi, düzenleme yetkisiyle aynı kuralları izler (bkz. general/page.py ->
    # update_bank_account_page): kişisel hesabı yalnızca sahibi, sandık hesabını yalnızca
    # sandıkta yazma yetkisi olan siler.
    if bank_account.web_user_ref:
        if bank_account.web_user_ref != deleted_by:
            raise UnauthorizedBankAccountOperation("Başkasının banka hesabını silemezsiniz!", create_log=True)
    elif bank_account.sandik_ref:
        if not deleted_by.has_permission(sandik=bank_account.sandik_ref, permission="write"):
            raise UnauthorizedBankAccountOperation("Sandıkta yazma yetkiniz bulunmamaktadır!", create_log=True)
    else:
        raise UnauthorizedBankAccountOperation("Sahibi belirsiz banka hesabı silinemez.", create_log=True)

    # if bank_account.is_primary:
    #     raise PrimaryBankAccountCannotBeDeleted("Birincil banka hesabı silinemez.")

    return db.delete_bank_account(bank_account=bank_account, deleted_by=deleted_by)
