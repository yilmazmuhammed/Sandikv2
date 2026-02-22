import os

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", '.env'))
from pony.orm import select
from pony.orm.core import db_session, desc

from sandik.utils.db_models import Sandik, Debt, PieceOfDebt


# 1 - pod.amount == 0 olmamalı -> pod.amount == 0 olanlar silinecek
# 2 - debt.get_unpaid_amount() == 0 ise bütün pod'lar için pod.get_unpaid_amount() == 0 olmalı ->
#     if pod.debt_ref.get_unpaid_amount() == 0 ise pod.paid_amount = pod.amount yapılacak
#     -> pod.amount == 0 olanlar silinecek
# 3 - pod.amount < 0 olmamalı -> pod.amount < 0 olanlar debt'in diğer pod'larına dağıtılacak
#     -> pod.amount == 0 olanlar silinecek
# 4 - pod.member_ref.is_active == False ise ve pod.get_unpaid_amount() > 0 ise
#     kalan kısım şu an ki güven bağlarına dağıtılır
#     -> pod.amount == 0 olanlar silinecek
# 5 - debt.amount == debt.pods_set.amount.sum() olmalı
# 6 - debt.paid_amount == debt.pods_set.paid_amount.sum() olmalı

def check_fully_distributed_all_debts():
    for debt in select(d for d in Debt.select() if d.member_ref.sandik_ref.type == Sandik.TYPE.WITH_TRUST_RELATIONSHIP):
        if debt.amount != select(pod.amount for pod in debt.piece_of_debts_set).sum():
            print("debt:", debt.to_extended_dict())
            for pod in debt.piece_of_debts_set:
                print("pod:", pod.to_dict())
            raise Exception("Invalid state")


def check_fully_distributed_paid_amounts_for_all_debts():
    for debt in select(d for d in Debt.select() if d.member_ref.sandik_ref.type == Sandik.TYPE.WITH_TRUST_RELATIONSHIP):
        if debt.get_paid_amount() != select(pod.paid_amount for pod in debt.piece_of_debts_set).sum():
            print("debt:", debt.to_extended_dict())
            for pod in debt.piece_of_debts_set:
                print("pod:", pod.to_dict())
            raise Exception("Invalid state")


def check_all():
    check_fully_distributed_all_debts()
    check_fully_distributed_paid_amounts_for_all_debts()


def step_1_clear_empty_pods(print_prefix=""):
    check_all()

    query = select(pod for pod in PieceOfDebt.select() if pod.amount == 0 and pod.paid_amount == 0)
    if query.count() != 0:
        print(f"{print_prefix}{query.count()} pods deleting because they are empty")
        query.delete(bulk=True)

    query = select(pod for pod in PieceOfDebt.select() if pod.amount == 0)
    if query.count() != 0:
        print(f"{print_prefix}  {query.count()} pods not deleted because their paid amount are not zero")

    check_all()


def step_2_fix_paid_amount_already_paid_debts():
    check_all()

    query = select(pod for pod in PieceOfDebt.select() if
                   pod.debt_ref.get_unpaid_amount() == 0 and pod.amount != pod.paid_amount)
    if query.count() != 0:
        print(f"{query.count()} pods updating because their debt is already paid but they not paid")
        for pod in query:
            pod.paid_amount = pod.amount

    step_1_clear_empty_pods("  ")

    check_all()


def step_3_redistributed_negative_pod_to_another_pots_of_debt():
    check_all()

    query = select(pod for pod in PieceOfDebt.select() if pod.amount < 0)
    if query.count() != 0:
        print(f"{query.count()} pods redistributing to another pods of same debt because they is negative")
        debts_of_negative_pods = list(select(pod.debt_ref for pod in query))
        for pod in query:
            pod.amount = 0
        print(f"  {len(debts_of_negative_pods)} debts updating...")
        for debt in debts_of_negative_pods:
            sorted_pods = debt.piece_of_debts_set.order_by(lambda p: desc(p.amount))
            old_total_amount_of_pods = select(pod.amount for pod in sorted_pods).sum()
            undistributed_amount = debt.amount
            for pod in sorted_pods:
                pod.amount = int(debt.amount * (pod.amount / old_total_amount_of_pods))
                undistributed_amount -= pod.amount
            for pod in sorted_pods:
                pod.amount += 1
                undistributed_amount -= 1
                if undistributed_amount <= 0:
                    break
            debt.update_pieces_of_debt()

    step_1_clear_empty_pods("  ")

    check_all()


def step_4_redistributed_pods_of_passive_member_to_trusted_links():
    check_all()

    query = select(
        pod for pod in PieceOfDebt.select() if pod.member_ref.is_active == False and pod.get_unpaid_amount() > 0)
    if query.count() != 0:
        print(f"{query.count()} pods redistributing to trusted_links because their member is passive")
        debts = select(pod.debt_ref for pod in query).distinct()
        for debt in debts:
            amount_to_distribute = select(
                pod.amount for pod in debt.piece_of_debts_set if pod.member_ref.is_active == False).sum()
            for pod in select(pod for pod in debt.piece_of_debts_set if pod.member_ref.is_active == False):
                pod.amount = 0
                pod.paid_amount = 0

            if amount_to_distribute > debt.member_ref.max_borrow_amount_from_accepted_trust_links():
                raise Exception("Dağıtılamıyor")

            # Önce borç sahibine yazılsın
            debt_member = debt.member_ref
            temp_amount = min(debt_member.get_balance(), amount_to_distribute)
            if temp_amount > 0:
                PieceOfDebt(member_ref=debt_member, debt_ref=debt,
                            amount=temp_amount)
                amount_to_distribute -= temp_amount

            # Eğer hala açık varsa güven bağlarına yazılsın
            if amount_to_distribute > 0:
                positive_links = [tl for tl in debt.member_ref.accepted_trust_links() if
                                  tl.other_member(debt_member).get_balance() > 0]
                sorted_links = sorted(positive_links, key=lambda tl: tl.other_member(debt_member).get_balance())
                remaining_link_count = len(sorted_links)
                for tl in sorted_links:
                    temp_amount = amount_to_distribute // remaining_link_count
                    temp_amount = min(temp_amount, tl.other_member(debt_member).get_balance())
                    if temp_amount > 0:
                        PieceOfDebt(member_ref=tl.other_member(debt_member), debt_ref=debt,
                                    amount=temp_amount)
                        amount_to_distribute -= temp_amount
                    remaining_link_count -= 1
            debt.update_pieces_of_debt()

    step_1_clear_empty_pods("  ")

    check_all()


if __name__ == '__main__':
    with db_session:
        step_1_clear_empty_pods()
    with db_session:
        step_2_fix_paid_amount_already_paid_debts()
    with db_session:
        step_3_redistributed_negative_pod_to_another_pots_of_debt()
    with db_session:
        step_4_redistributed_pods_of_passive_member_to_trusted_links()
    with db_session:
        check_all()
