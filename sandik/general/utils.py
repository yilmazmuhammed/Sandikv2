from decimal import Decimal

from sandik.general import db
from sandik.general.exceptions import BankAccountNotFound, PrimaryBankAccountCannotBeDeleted, \
    UnauthorizedBankAccountOperation
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
    sandik_totals = {member.id: Decimal(0) for member in members}
    for member in members:
        for payment in transaction_utils.get_payments(whose=member, is_fully_paid=False):
            unpaid_amount = payment.get_unpaid_amount()
            if unpaid_amount <= 0:
                continue
            row = payments_matrix.setdefault(payment.term, {})
            row[member.id] = row.get(member.id, Decimal(0)) + unpaid_amount
            sandik_totals[member.id] += unpaid_amount

    payment_rows = []
    for term in sorted(payments_matrix.keys()):
        cells = payments_matrix[term]
        payment_rows.append({
            "term": term,
            "cells": cells,
            "total": sum(cells.values()),
        })

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

    net_sandik_totals = {member.id: sandik_totals[member.id] - undistributed_amounts[member.id]
                         for member in members}

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
        "payment_rows": payment_rows,
        "sandik_totals": net_sandik_totals,
        "grand_total": sum(net_sandik_totals.values()) if net_sandik_totals else Decimal(0),
        "undistributed_row": undistributed_row,
        "current_period": period_utils.current_period(),
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
