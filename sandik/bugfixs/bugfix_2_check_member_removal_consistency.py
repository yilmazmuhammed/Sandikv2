"""
Üye/hisse silme sırasında oluşan tutarsızlıkları TESPİT eder. SALT OKUNURDUR, hiçbir şey yazmaz.

Arka plan:
    Düzeltmeden önce `remove_member_from_sandik()` iade edilecek tutarı, ödemesi tamamlanmamış
    aidatlar silinmeden ÖNCE hesaplıyordu. Kısmi ödenmiş bir aidata yatan para hem "ödenmiş aidat"
    (negatif aidat + alt makbuz) hem de "işleme konmamış para" (retracted) olarak iki kez iade
    ediliyor, iade para çıkışı aşırı dağıtılıyor ve ERRCODE 0013 alınıyordu.
    Silme yarıda kaldığı için üye pasife çekilmiyor, tekrar silinmeye çalışılınca da
    negatif tutarlı bir para çıkışı oluşuyordu.

Kullanım:
    python sandik/bugfixs/bugfix_2_check_member_removal_consistency.py            # tüm sandıkları tara
    python sandik/bugfixs/bugfix_2_check_member_removal_consistency.py <member_id>  # tek üyeyi dök
"""
import os
import sys

# `sandik` paketini bulabilmek için depo kökü (Sandikv2/) sys.path'e ekleniyor.
# Bu sayede script hangi dizinden çalıştırılırsa çalıştırılsın import'lar çalışır.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", '.env'))

from pony.orm import select
from pony.orm.core import db_session

from sandik.utils.db_models import Member, MoneyTransaction, Contribution, Installment, SubReceipt


def _mt_line(mt: MoneyTransaction):
    return (f"    MT#{mt.id} {mt.date} {MoneyTransaction.TYPE.strings.get(mt.type, mt.type)} "
            f"tutar={mt.amount} dağıtılan={mt.distributed_amount()} "
            f"dağıtılmamış={mt.get_undistributed_amount()} "
            f"is_fully_distributed={mt.is_fully_distributed} detay={mt.detail!r}")


def _sr_line(sr: SubReceipt):
    if sr.contribution_ref:
        ref = f"aidat#{sr.contribution_ref.id}(dönem={sr.contribution_ref.term}, tutar={sr.contribution_ref.amount})"
    elif sr.installment_ref:
        ref = f"taksit#{sr.installment_ref.id}(dönem={sr.installment_ref.term})"
    elif sr.debt_ref:
        ref = f"borç#{sr.debt_ref.id}"
    elif sr.expense_retracted_ref:
        ref = f"geri-alınmış#{sr.expense_retracted_ref.id} (gider tarafı)"
    elif sr.revenue_retracted_ref:
        ref = f"geri-alınmış#{sr.revenue_retracted_ref.id} (gelir tarafı)"
    else:
        ref = "BAĞLANTISIZ (!)"
    return f"        SR#{sr.id} tutar={sr.amount} -> {ref}"


def dump_member(member: Member):
    """Bir üyenin tüm para işlemlerini, alt makbuzlarını ve hisse durumunu ekrana döker."""
    print("=" * 100)
    print(f"Üye#{member.id} {member.web_user_ref.name_surname if member.web_user_ref else '-'} "
          f"| sandık={member.sandik_ref.name} (#{member.sandik_ref.id}, {member.sandik_ref.type_str()}) "
          f"| aktif={member.is_active}")
    print(f"  ödenen aidat toplamı  : {member.sum_of_paid_contributions()}")
    print(f"  işleme konmamış para  : {member.total_of_undistributed_amount()}")
    print(f"  bakiye (get_balance)  : {member.get_balance()}")
    print(f"  verdiği borç / ödenmemiş: {member.get_loaned_amount()} / {member.get_unpaid_amount_of_loaned()}")

    print("  HİSSELER:")
    for share in member.shares_set.order_by(lambda s: s.share_order_of_member):
        print(f"    Hisse#{share.id} sıra={share.share_order_of_member} aktif={share.is_active} "
              f"ödenen aidat={share.sum_of_paid_contributions()}")

    print("  PARA İŞLEMLERİ:")
    for mt in member.money_transactions_set.order_by(lambda m: m.id):
        print(_mt_line(mt))
        for sr in mt.sub_receipts_set.order_by(lambda s: s.id):
            print(_sr_line(sr))

    print("  NEGATİF / SIFIR TUTARLI AİDATLAR:")
    for c in select(c for c in Contribution if c.share_ref.member_ref == member and c.amount <= 0).order_by(
            lambda c: c.id):
        print(f"    Aidat#{c.id} dönem={c.term} tutar={c.amount} ödenen={c.get_paid_amount()} "
              f"ödenmemiş={c.get_unpaid_amount()} tamamen_ödendi={c.is_fully_paid}")
    print()


def find_problems():
    """Tutarsızlık şüphesi olan üyeleri bulur. Hiçbir şey değiştirmez."""
    problems = {}

    def add(member, msg):
        problems.setdefault(member, []).append(msg)

    # 1) Aşırı dağıtılmış para işlemi (ERRCODE 0013'ün nedeni)
    for mt in MoneyTransaction.select():
        undistributed = mt.get_undistributed_amount()
        if undistributed < 0:
            add(mt.member_ref, f"MT#{mt.id} aşırı dağıtılmış (dağıtılmamış={undistributed})")
        if mt.amount < 0:
            add(mt.member_ref, f"MT#{mt.id} negatif tutarlı para işlemi (tutar={mt.amount})")
        elif mt.amount == 0:
            # Zararsız: iade edilecek bir tutar yokken oluşturulmuş boş kayıt. Sadece görsel kirlilik.
            add(mt.member_ref, f"MT#{mt.id} sıfır tutarlı para işlemi (zararsız, detay={mt.detail!r})")
        if mt.is_fully_distributed != (undistributed == 0):
            add(mt.member_ref, f"MT#{mt.id} is_fully_distributed={mt.is_fully_distributed} "
                               f"ama dağıtılmamış={undistributed}")

    # 2) Yarıda kalmış silme: aktif üye ama hiç aktif hissesi yok
    for member in Member.select(lambda m: m.is_active):
        if member.shares_set.count() > 0 and member.get_active_shares().count() == 0:
            add(member, "Üye aktif görünüyor ama aktif hissesi yok (silme yarıda kalmış olabilir)")

    # 3) Pasif üyenin bakiyesi sıfır olmalı
    for member in Member.select(lambda m: not m.is_active):
        balance = member.get_balance()
        if balance != 0:
            add(member, f"Pasif üyenin bakiyesi sıfır değil: {balance}")

    # 4) Fazla ödenmiş aidat/taksit
    for c in Contribution.select():
        if c.get_unpaid_amount() < 0:
            add(c.share_ref.member_ref, f"Aidat#{c.id} fazla ödenmiş ({c.get_unpaid_amount()})")
    for i in Installment.select():
        if i.get_unpaid_amount() < 0:
            add(i.debt_ref.share_ref.member_ref, f"Taksit#{i.id} fazla ödenmiş ({i.get_unpaid_amount()})")

    return problems


if __name__ == '__main__':
    with db_session:
        if len(sys.argv) > 1:
            dump_member(Member[int(sys.argv[1])])
        else:
            found = find_problems()
            if not found:
                print("Tutarsızlık bulunamadı.")
            for member, messages in found.items():
                print("-" * 100)
                print(f"Üye#{member.id} "
                      f"{member.web_user_ref.name_surname if member.web_user_ref else '-'} "
                      f"| sandık={member.sandik_ref.name} | aktif={member.is_active}")
                for message in messages:
                    print(f"  - {message}")
            print()
            print("Ayrıntılı döküm için: "
                  "python sandik/bugfixs/bugfix_2_check_member_removal_consistency.py <member_id>")
