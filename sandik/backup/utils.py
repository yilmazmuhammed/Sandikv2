from datetime import datetime

from sandik.auth import db as auth_db
from sandik.backup import db
from sandik.sandik import utils as sandik_utils, db as sandik_db
from sandik.transaction import utils as transaction_utils
from sandik.utils.db_models import MoneyTransaction, Sandik


def backup_database():
    backup_data = {}
    for table in db.DATABASE_TABLES_TO_BACKUP_WITH_ORDER:
        backup_data[table.__name__] = db.backup_table(table, included_relation_sets=db.INCLUDED_RELATION_SETS)

    return backup_data


def create_or_update_admin_users(admin_users_data):
    for user_data in admin_users_data:
        user = auth_db.get_web_user(email_address=user_data["email_address"])
        if user:
            auth_db.update_web_user(user, updated_by=auth_db.get_or_create_bot_user("backup_manager"),
                                    password_hash=user_data["password_hash"])
        else:
            user_data.pop("id")
            auth_db.create_web_user(**user_data, created_by=auth_db.get_or_create_bot_user("backup_manager"))


def restore_database(backup_data):
    # TODO bütün satırlar import edildikten sonra before_insert gibi fonksiyonların çalışması lazım

    for table, relations in db.EXCLUDED_RELATIONS.items():
        for relation in relations:
            for row in backup_data[table.__name__]:
                row.pop(relation)

    admin_users = auth_db.get_admin_web_users()
    admin_users_data = [user.to_dict() for user in admin_users]

    db.reset_database(db.DATABASE_TABLES_TO_BACKUP_WITH_ORDER)

    for table in db.DATABASE_TABLES_TO_BACKUP_WITH_ORDER:
        db.restore_table(table=table, rows=backup_data[table.__name__])

    db.recalculate_is_fully_paid_for_all_payments()

    create_or_update_admin_users(admin_users_data=admin_users_data)


def create_sandik_from_sandikv1_data(data, created_by):
    from passlib.hash import pbkdf2_sha256 as hasher

    # Sandık oluştur
    sandik = sandik_db.create_sandik(
        name=data["sandik"]["name"], contribution_amount=data["sandik"]["contribution_amount"],
        detail=data["sandik"]["detail"], created_by=created_by, type=Sandik.TYPE.CLASSIC,
        date_of_opening=datetime.strptime(data["sandik"]["date_of_opening"], "%Y-%m-%d").date()
    )

    # Kullanıcıları oluştur
    web_users = {}
    for web_user in data["web_users"]:
        print("web_user:", web_user)
        if not web_user.get("email_address", None):
            web_user["email_address"] = f"{web_user['username']}@sandik.com"
        new_web_user = auth_db.get_web_user(email_address=web_user["email_address"])
        if not new_web_user:
            new_web_user = auth_db.create_web_user(email_address=web_user["email_address"],
                                                   password_hash=hasher.hash(f'{web_user["username"]}pw'),
                                                   name=web_user["name"], surname=web_user["surname"],
                                                   created_by=created_by)
        web_users[web_user["username"]] = new_web_user

    # Sandık üyelerini oluştur
    members = {}
    for member in data["members"]:
        print("member:", member)
        new_member = sandik_utils.add_member_to_sandik(
            sandik=sandik, web_user=web_users[member["username"]], added_by=created_by,
            date_of_membership=datetime.strptime(member["date_of_membership"], "%Y-%m-%d").date(),
            contribution_amount=member["contribution_amount"], detail=member["detail"], number_of_share=0
        )
        members[member["id"]] = new_member

    # Hisseler oluşturulur
    shares = {}
    for share in data["shares"]:
        print("share:", share)
        new_share = sandik_utils.add_share_to_member(
            member=members[share["member_id"]], added_by=created_by, create_contributions=False,
            date_of_opening=datetime.strptime(share["date_of_membership"], "%Y-%m-%d").date(),
            force=True
        )
        shares[share["id"]] = new_share

    # Aidatlar ve para girişlerini oluşturulur
    for contribution in data["contributions"]:
        print("contribution:", contribution)
        share = shares[contribution["share_id"]]
        amount = contribution["amount"]
        contribution_created_by = web_users[contribution["created_by"]]
        new_contribution = transaction_utils.add_custom_contribution(
            amount=amount, period=contribution["period"], share=share, created_by=contribution_created_by
        )
        if amount > 0:
            mt_type = MoneyTransaction.TYPE.REVENUE
            transaction_utils.add_money_transaction(
                member=share.member_ref, amount=abs(amount), created_by=contribution_created_by,
                date=datetime.strptime(contribution["date"], "%Y-%m-%d").date(),
                type=mt_type, payments=[new_contribution], use_untreated_amount=None,
                pay_future_payments=False, creation_type=MoneyTransaction.CREATION_TYPE.BY_SANDIKV1_DATA,
                detail=contribution["detail"]
            )
        else:
            sandik_utils.remove_share_from_member(
                share=share, removed_by=contribution_created_by,
                removed_date=datetime.strptime(contribution["date"], "%Y-%m-%d").date()
            )

    money_transactions_of_debts = {}
    # Borçları ve para çıkışlarını oluşturulur
    for debt in data["debts"]:
        print("debt:", debt)
        share = shares[debt["share_id"]]
        amount = debt["amount"]
        debt_created_by = web_users[debt["created_by"]]
        debt_mt = transaction_utils.add_money_transaction(
            member=share.member_ref, amount=amount, created_by=debt_created_by,
            date=datetime.strptime(debt["date"], "%Y-%m-%d").date(),
            type=MoneyTransaction.TYPE.EXPENSE, use_untreated_amount=False,
            pay_future_payments=None, creation_type=MoneyTransaction.CREATION_TYPE.BY_SANDIKV1_DATA,
            detail=debt["detail"], number_of_installment=debt["number_of_installment"], share=share
        )
        money_transactions_of_debts[debt["id"]] = debt_mt

    # Ödemeler ve para girişlerini oluşturulur
    for payment in data["payments"]:
        print("payment:", payment)
        share = shares[payment["share_id"]]
        amount = payment["amount"]
        payment_created_by = web_users[payment["created_by"]]
        installments = money_transactions_of_debts[
            payment["debt_id"]].sub_receipts_set.select().get().debt_ref.installments_set
        transaction_utils.add_money_transaction(
            member=share.member_ref, amount=amount, created_by=payment_created_by,
            date=datetime.strptime(payment["date"], "%Y-%m-%d").date(),
            type=MoneyTransaction.TYPE.REVENUE, payments=installments, use_untreated_amount=False,
            pay_future_payments=None, creation_type=MoneyTransaction.CREATION_TYPE.BY_SANDIKV1_DATA,
            detail=payment["detail"]
        )

    # Ödemeler ve para girişlerini oluşturulur
    for other in data["others"]:
        print("other:", other)
        share = shares[other["share_id"]]
        amount = other["amount"]
        other_created_by = web_users[other["created_by"]]
        if amount > 0:
            mt_type = MoneyTransaction.TYPE.REVENUE
        else:
            mt_type = MoneyTransaction.TYPE.EXPENSE
        transaction_utils.add_money_transaction(
            member=share.member_ref, amount=abs(amount), created_by=other_created_by,
            date=datetime.strptime(other["date"], "%Y-%m-%d").date(),
            type=mt_type, use_untreated_amount=True, dont_treate=True,
            pay_future_payments=False, creation_type=MoneyTransaction.CREATION_TYPE.BY_SANDIKV1_DATA,
            detail=other["detail"]
        )

    # Hissesi olmayan üyeler silnir
    for member in sandik.members_set:
        print(member.web_user_ref.name_surname, member.get_active_shares().count())
        if member.get_active_shares().count() == 0:
            sandik_utils.remove_member_from_sandik(member=member, removed_by=created_by)

    return None


data = {
    "sandik": {
        "name": "",
        "contribution_amount": int,
        "detail": "",
        "date_of_opening": "%Y-%m-%d",
    },
    "web_users": [{
        "email_address": "",
        "username": "",
        "name": "",
        "surname": ""
    }],
    "members": [{
        "id": int,
        "username": "",
        "date_of_membership": "%Y-%m-%d",
        "contribution_amount": int,
        "detail": ""
    }],
    "shares": [{
        "id": int,
        "member_id": int,
        "date_of_membership": "%Y-%m-%d",
    }],
    "contributions": [{
        "share_id": int,
        "amount": int,
        "period": "",
        "created_by": int,
        "date": "%Y-%m-%d",
        "detail": "",
    }],
    "debts": [{
        "id": int,
        "share_id": int,
        "amount": int,
        "created_by": int,
        "date": "%Y-%m-%d",
        "detail": "",
    }],
    "payments": [{
        "share_id": int,
        "amount": "",
        "created_by": "",
        "date": "",
        "detail": "",
        "debt_id": int
    }],
    "others": [{
        "share_id": int,
        "amount": "",
        "created_by": "",
        "date": "",
        "detail": "",
    }],
}
