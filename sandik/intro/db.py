"""Tanıtım/istatistik sayfaları için salt okunur sorgular.

Diğer `db.py` dosyalarının aksine burada veri değiştirilmez, dolayısıyla `Log` kaydı da
oluşturulmaz. Bütün fonksiyonlar toplu (aggregate) sonuç döndürür; tek bir üyeye/sandığa ait
kişisel bilgi dışarı verilmez.
"""
from pony.orm import count, exists, max as pony_max, select, sum as pony_sum

from sandik.utils.db_models import Contribution, Debt, Installment, Member, MoneyTransaction, Sandik, Share, \
    SubReceipt, WebUser


def select_sandiks(**kwargs):
    return Sandik.select(**kwargs)


def active_member_counts_by_sandik() -> dict:
    """{sandik_id: aktif üye sayısı}"""
    return dict(select((m.sandik_ref.id, count(m)) for m in Member if m.is_active))


def money_transaction_counts_by_sandik() -> dict:
    """{sandik_id: para giriş/çıkış sayısı}"""
    return dict(select((mt.member_ref.sandik_ref.id, count(mt)) for mt in MoneyTransaction))


def last_money_transaction_dates_by_sandik() -> dict:
    """{sandik_id: son para hareketinin tarihi}"""
    return dict(select((mt.member_ref.sandik_ref.id, pony_max(mt.date)) for mt in MoneyTransaction))


def count_active_members(sandiks) -> int:
    return select(m for m in Member if m.is_active and m.sandik_ref in sandiks).count()


def count_web_users_of_sandiks(sandiks) -> int:
    """Verilen sandıkların en az birinde aktif üyeliği olan site kullanıcısı sayısı.

    Kayıt olup hiçbir sandıkta üye olmamış (ya da üyeliği kapatılmış) kullanıcılar sayılmaz.
    """
    return select(
        wu for wu in WebUser
        if exists(m for m in wu.members_set if m.is_active and m.sandik_ref in sandiks)
    ).count()


def count_active_shares(sandiks) -> int:
    return select(s for s in Share if s.is_active and s.member_ref.sandik_ref in sandiks).count()


def count_money_transactions(sandiks) -> int:
    return select(mt for mt in MoneyTransaction if mt.member_ref.sandik_ref in sandiks).count()


def count_contributions(sandiks) -> int:
    return select(c for c in Contribution if c.share_ref.member_ref.sandik_ref in sandiks).count()


def count_installments(sandiks) -> int:
    return select(i for i in Installment if i.debt_ref.share_ref.member_ref.sandik_ref in sandiks).count()


def count_debts(sandiks) -> int:
    return select(d for d in Debt if d.share_ref.member_ref.sandik_ref in sandiks).count()


def sum_of_debts(sandiks):
    """Sandıkların kuruluşundan bugüne üyelere verilmiş toplam borç."""
    return select(d.amount for d in Debt if d.share_ref.member_ref.sandik_ref in sandiks).sum()


def sum_of_paid_contributions(sandiks):
    return select(sr.amount for sr in SubReceipt
                  if sr.contribution_ref and sr.money_transaction_ref.member_ref.sandik_ref in sandiks).sum()


def sum_of_paid_installments(sandiks):
    return select(sr.amount for sr in SubReceipt
                  if sr.installment_ref and sr.money_transaction_ref.member_ref.sandik_ref in sandiks).sum()


def sum_of_revenue_money_transactions(sandiks):
    """Üyelerin sandıklara yatırdığı toplam para (aidat + taksit + dağıtılmamış tutarlar)."""
    return select(mt.amount for mt in MoneyTransaction
                  if mt.type == MoneyTransaction.TYPE.REVENUE and mt.member_ref.sandik_ref in sandiks).sum()


def average_contribution_amount(sandiks):
    return select(m.contribution_amount for m in Member if m.is_active and m.sandik_ref in sandiks).avg()


def debt_statistics_by_year(sandiks) -> list:
    """[(yıl, verilen borç toplamı, borç adedi), ...] — yılı artan sırada.

    Borcun tarihi olarak, borcun verildiği para çıkışının (`MoneyTransaction`) tarihi kullanılır;
    `Debt` üzerinde ayrı bir tarih alanı yoktur.
    """
    return select(
        (d.sub_receipt_ref.money_transaction_ref.date.year, pony_sum(d.amount), count(d))
        for d in Debt if d.share_ref.member_ref.sandik_ref in sandiks
    ).order_by(1)[:]
