from flask import Blueprint, jsonify, request, g

from sandik.sandik import db as sandik_db
from sandik.sandik.exceptions import NoValidRuleFound
from sandik.sandik.requirement import sandik_authorization_required, member_required
from sandik.transaction import utils
from sandik.transaction.exceptions import MaximumDebtAmountExceeded
from sandik.utils.db_models import MoneyTransaction

transaction_api_bp = Blueprint('transaction_api_bp', __name__)


@transaction_api_bp.route('odenmemis-borclar')
@sandik_authorization_required("read")
def get_unpaid_debts_of_member_api(sandik_id):
    if not request.args.get("member"):
        return jsonify(result=False, msg="'member' parametresi ile member_id'nin gonderilmesi gerekmektedir.")

    member = sandik_db.get_member(id=request.args.get("member"))
    if not member:
        return jsonify(result=False, msg="Üye bulunamadı")

    debts = [debt.to_extended_dict() for debt in member.get_unpaid_debts()]
    return jsonify(result=True, member_id=member.id, debts=debts)


@transaction_api_bp.route('borc-detaylarini-hesapla/uye-<int:member_id>')
@sandik_authorization_required("read", allow_member=True)
@member_required
def get_debt_distribution_api(sandik_id, member_id):
    amount = request.args.get("amount")
    if not amount:
        return jsonify(result=False, msg="'amount' parametresi ile borç alınacak miktarın girilmesi gerekmektedir.")
    if not amount.isnumeric():
        return jsonify(result=False, msg="Borç alınacak miktarın sayısal olarak girilmesi gerekmektedir.")

    try:
        amount = int(amount)
        utils.validate_money_transaction_for_expense(
            mt_type=MoneyTransaction.TYPE.EXPENSE, use_untreated_amount=False,
            amount=amount, whose=g.member
        )
        share = request.args.get("share", None)
        debts = utils.get_debt_distribution(amount=amount, member=g.member, share=share)
        return jsonify(result=True, share=share, amount=amount, debts=debts)
    except (MaximumDebtAmountExceeded, NoValidRuleFound) as e:
        return jsonify(result=False, msg=str(e))
    except Exception as e:
        return jsonify(result=False, err_type=str(type(e)), msg=str(e))
