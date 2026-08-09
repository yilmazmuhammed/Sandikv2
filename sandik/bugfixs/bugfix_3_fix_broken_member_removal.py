"""
Yarıda kalmış / iki kez denenmiş üye silme işlemlerinin bıraktığı tutarsızlıkları ONARIR.

Arka plan:
    Düzeltmeden önce `remove_member_from_sandik()` iade edilecek tutarı, ödemesi tamamlanmamış
    aidatlar silinmeden ÖNCE hesaplıyordu. Kısmi ödenmiş bir aidata yatan para hem "ödenmiş aidat"
    (negatif aidat + alt makbuz) hem de "işleme konmamış para" ("geri alınmış" kaydı) olarak iki kez
    iade ediliyordu. Bunun sonucu:
      - iade para çıkışı aşırı dağıtılıyor (ERRCODE 0013) ve silme yarıda kalıyor,
      - üye pasife çekilemediği için ikinci kez silme denendiğinde negatif tutarlı bir
        "Üye ayrılışı" para çıkışı oluşuyordu.

Bu script iki şeyi yapar:
    1. Alt makbuzu olmayan, tutarı sıfır veya negatif olan para işlemlerini siler.
    2. Her hisse için oluşturulan iade aidatını (dönem "9999-01", negatif tutarlı) ve onun alt
       makbuzunu, o hisse için GERÇEKTEN ödenmiş aidat tutarına indirir. Fazla iade edilen kısım
       zaten "geri alınmış" kaydıyla iade edilmiş durumdadır.

Sonuçta üyenin toplam para girişi ile toplam para çıkışı eşitlenir ve bakiyesi 0 olur.

ÖNCE `bugfix_2_check_member_removal_consistency.py` ile durumu incele, ÖNCE VERİTABANI YEDEĞİ AL.

Kullanım:
    # Sadece ne yapılacağını göster (varsayılan, hiçbir şey yazmaz)
    python sandik/bugfixs/bugfix_3_fix_broken_member_removal.py <member_id> [<member_id> ...]

    # Gerçekten uygula
    python sandik/bugfixs/bugfix_3_fix_broken_member_removal.py <member_id> --fix
"""
import os
import sys

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", '.env'))

from pony.orm import select, flush, rollback, commit
from pony.orm.core import db_session

from sandik.auth import db as auth_db
from sandik.transaction import db as transaction_db
from sandik.utils.db_models import Member, MoneyTransaction, Contribution


def _report(member: Member, label):
    total_revenue = select(mt.amount for mt in member.money_transactions_set
                           if mt.type == MoneyTransaction.TYPE.REVENUE).sum()
    total_expense = select(mt.amount for mt in member.money_transactions_set
                           if mt.type == MoneyTransaction.TYPE.EXPENSE).sum()
    print(f"  [{label}] aktif={member.is_active} bakiye={member.get_balance()} "
          f"ödenen_aidat={member.sum_of_paid_contributions()} "
          f"işleme_konmamış={member.total_of_undistributed_amount()} "
          f"toplam_giriş={total_revenue} toplam_çıkış={total_expense}")


def check_invariants(member: Member):
    """Onarım sonrası sağlanması gereken koşullar. Sağlanmıyorsa sebeplerini döner."""
    problems = []
    for mt in member.money_transactions_set:
        if mt.get_undistributed_amount() < 0:
            problems.append(f"MT#{mt.id} hâlâ aşırı dağıtılmış ({mt.get_undistributed_amount()})")
        if mt.amount < 0:
            problems.append(f"MT#{mt.id} hâlâ negatif tutarlı ({mt.amount})")
    if not member.is_active and member.get_balance() != 0:
        problems.append(f"Pasif üyenin bakiyesi sıfır değil ({member.get_balance()})")
    return problems


def fix_member(member: Member, removed_by):
    _report(member, "önce")

    # 1) Alt makbuzu olmayan, tutarı sıfır veya negatif para işlemlerini sil
    for mt in list(member.money_transactions_set.order_by(lambda m: m.id)):
        if mt.amount <= 0 and mt.sub_receipts_set.count() == 0:
            print(f"    MT#{mt.id} siliniyor (tutar={mt.amount}, detay={mt.detail!r}, alt makbuz yok)")
            transaction_db.delete_money_transaction(money_transaction=mt, removed_by=removed_by)
    flush()

    # 2) Fazla iade edilen aidat tutarını düzelt
    for share in member.shares_set.order_by(lambda s: s.share_order_of_member):
        paid_in = select(sr.amount for sr in share.sub_receipts_set
                         if sr.contribution_ref and sr.money_transaction_ref.is_type_revenue()).sum()
        refunded = select(sr.amount for sr in share.sub_receipts_set
                          if sr.contribution_ref and sr.money_transaction_ref.is_type_expense()).sum()
        excess = refunded - paid_in

        if excess == 0:
            continue
        if excess < 0:
            print(f"    Hisse#{share.id}: iade ({refunded}) ödenenden ({paid_in}) AZ. "
                  f"Bu script bu durumu düzeltmez, elle incele.")
            continue

        print(f"    Hisse#{share.id}: iade edilen aidat={refunded}, gerçekte ödenen={paid_in} "
              f"-> {excess} fazla iade düzeltiliyor")
        for contribution in select(c for c in Contribution
                                   if c.share_ref == share and c.amount < 0).order_by(lambda c: c.id):
            for sub_receipt in contribution.sub_receipts_set.order_by(lambda sr: sr.id):
                reduction = min(excess, sub_receipt.amount)
                if reduction <= 0:
                    continue
                sub_receipt.amount -= reduction
                contribution.amount += reduction
                excess -= reduction
                print(f"        Aidat#{contribution.id} tutar -> {contribution.amount}, "
                      f"SR#{sub_receipt.id} tutar -> {sub_receipt.amount}")
                if excess == 0:
                    break
            contribution.recalculate_is_fully_paid()
            if excess == 0:
                break
        if excess != 0:
            print(f"    Hisse#{share.id}: {excess} kadar fazla iade düşülemedi, elle incele.")
    flush()

    for mt in member.money_transactions_set:
        mt.recalculate_is_fully_distributed()
    flush()

    _report(member, "sonra")
    return check_invariants(member)


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply_changes = "--fix" in sys.argv

    if not args:
        print(__doc__)
        sys.exit(1)

    if not apply_changes:
        print(">>> KURU ÇALIŞMA (dry-run): hiçbir değişiklik kaydedilmeyecek. "
              "Uygulamak için sonuna --fix ekleyin.\n")

    with db_session:
        bot = auth_db.get_or_create_bot_user(which="bugfix_manager")
        all_problems = {}
        for member_id in args:
            member = Member[int(member_id)]
            print(f"Üye#{member.id} "
                  f"{member.web_user_ref.name_surname if member.web_user_ref else '-'} "
                  f"| sandık={member.sandik_ref.name}")
            problems = fix_member(member, removed_by=bot)
            if problems:
                all_problems[member.id] = problems
            print()

        if all_problems:
            print("Onarım sonrası hâlâ sorun var, HİÇBİR DEĞİŞİKLİK KAYDEDİLMEDİ:")
            for member_id, problems in all_problems.items():
                for problem in problems:
                    print(f"  Üye#{member_id}: {problem}")
            rollback()
        elif apply_changes:
            commit()
            print("Değişiklikler kaydedildi.")
        else:
            rollback()
            print("Kuru çalışma bitti, değişiklikler geri alındı.")
