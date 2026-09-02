from flask import Blueprint, jsonify, request, g

from sandik.sandik import db as sandik_db
from sandik.sandik.exceptions import NoValidRuleFound
from sandik.sandik.requirement import sandik_authorization_required, member_required
from sandik.transaction import utils
from sandik.transaction.exceptions import MaximumDebtAmountExceeded
from sandik.utils import money
from sandik.utils.db_models import MoneyTransaction

transaction_api_bp = Blueprint('transaction_api_bp', __name__)


@transaction_api_bp.route('odenmemis-borclar')
@sandik_authorization_required("read")
def get_unpaid_debts_of_member_api(sandik_id):
    if not request.args.get("member"):
        return jsonify(result=False, msg="'member' parametresi ile member_id'nin gonderilmesi gerekmektedir.")

    member = sandik_db.get_member(id=request.args.get("member"), sandik_ref=g.sandik)
    if not member:
        return jsonify(result=False, msg="Üye bulunamadı")

    debts = [debt.to_extended_dict() for debt in member.get_unpaid_debts()]
    return jsonify(result=True, member_id=member.id, debts=debts)


@transaction_api_bp.route('odenmemis-aidatlar')
@sandik_authorization_required("read")
def get_unpaid_contributions_of_member_api(sandik_id):
    if not request.args.get("member"):
        return jsonify(result=False, msg="'member' parametresi ile member_id'nin gonderilmesi gerekmektedir.")

    member = sandik_db.get_member(id=request.args.get("member"), sandik_ref=g.sandik)
    if not member:
        return jsonify(result=False, msg="Üye bulunamadı")

    contributions = [contribution.to_extended_dict() for contribution in member.get_unpaid_contributions()]
    return jsonify(result=True, member_id=member.id, contributions=contributions)


@transaction_api_bp.route('borc-detaylarini-hesapla/uye-<int:member_id>')
@sandik_authorization_required("read", allow_member=True)
@member_required
def get_debt_distribution_api(sandik_id, member_id):
    amount = request.args.get("amount")
    if not amount:
        return jsonify(result=False, msg="'amount' parametresi ile borç alınacak miktarın girilmesi gerekmektedir.")
    # `isnumeric()` ondalıklı tutarları ("0.5") reddediyordu; altın gibi birimlerde bu, borç
    # dağılımının hiç hesaplanamaması demekti.
    amount = money.parse_amount(amount)
    if amount is None:
        return jsonify(result=False, msg="Borç alınacak miktarın sayısal olarak girilmesi gerekmektedir.")

    # 'share' parametresi, üyenin hissesine ait bir entity'ye çevrilmelidir;
    # get_debt_distribution() gelen değeri Share nesnesi olarak kullanır.
    share = None
    share_id = request.args.get("share")
    if share_id:
        if not share_id.isnumeric():
            return jsonify(result=False, msg="'share' parametresi sayısal olarak girilmelidir.")
        share = sandik_db.get_share(id=int(share_id), member_ref=g.member)
        if not share:
            return jsonify(result=False, msg="Hisse bulunamadı")

    try:
        utils.validate_money_transaction_for_expense(
            mt_type=MoneyTransaction.TYPE.EXPENSE, use_untreated_amount=False,
            amount=amount, whose=share or g.member
        )
        debts = utils.get_debt_distribution(amount=amount, member=g.member, share=share)
        return jsonify(result=True, share=share.id if share else None, amount=amount, debts=debts)
    except (MaximumDebtAmountExceeded, NoValidRuleFound) as e:
        return jsonify(result=False, msg=str(e))
    except Exception as e:
        return jsonify(result=False, err_type=str(type(e)), msg=str(e))
