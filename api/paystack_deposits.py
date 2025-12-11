# api/paystack_deposits.py

import uuid
import decimal
import requests
import hashlib
import hmac
import json

from django.conf import settings
from django.db import transaction as db_transaction
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .models import Transaction
from .wallet import credit_user_wallet

# ------------------------------
# CONFIG
# ------------------------------

PAYSTACK_BASE = "https://api.paystack.co"
PAYSTACK_SECRET = settings.PAYSTACK_SECRET_KEY


def paystack_headers():
    return {
        "Authorization": f"Bearer {PAYSTACK_SECRET}",
        "Content-Type": "application/json",
    }


# ------------------------------
# INITIATE DEPOSIT
# ------------------------------

class PaystackDepositView(APIView):
    """
    Create a payment and return the Paystack checkout link
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        raw_amount = request.data.get("amount")

        try:
            amount = decimal.Decimal(raw_amount)
            if amount <= 0:
                raise ValueError()
        except Exception:
            return Response({"error": "Invalid amount"}, status=400)

        reference = str(uuid.uuid4())

        # Save pending transaction
        txn = Transaction.objects.create(
            user=user,
            amount=amount,
            payment_method="BANK",
            currency="NGN",
            status="PENDING",
            reference=reference,
        )

        payload = {
            "email": user.email,
            "amount": int(amount * 100),  # Paystack expects KOBO
            "reference": reference,
            "callback_url": request.data.get("redirect_url"),
        }

        response = requests.post(
            f"{PAYSTACK_BASE}/transaction/initialize",
            headers=paystack_headers(),
            json=payload,
            timeout=10,
        )

        data = response.json()

        if not data.get("status"):
            txn.status = "FAILED"
            txn.save()
            return Response(data, status=400)

        return Response({
            "message": "Payment initialized",
            "reference": reference,
            "checkout_url": data["data"]["authorization_url"],
        })













# api/paystack_deposits.py (CONT.)

class PaystackVerifyView(APIView):
    """
    Final verification endpoint
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        reference = request.data.get("reference")

        if not reference:
            return Response({"error": "reference required"}, status=400)

        try:
            txn = Transaction.objects.get(reference=reference)
        except Transaction.DoesNotExist:
            return Response({"error": "Transaction not found"}, status=404)

        if txn.status == "SUCCESS":
            return Response({"status": "ALREADY_VERIFIED"})

        response = requests.get(
            f"{PAYSTACK_BASE}/transaction/verify/{reference}",
            headers=paystack_headers(),
            timeout=10,
        )

        data = response.json()

        if not data.get("status"):
            return Response({"error": "Paystack verification failed"}, status=502)

        ps_data = data["data"]

        if ps_data["status"] != "success":
            return Response({"error": "Payment not successful"}, status=400)

        # Confirm amount & currency
        paid_amount = decimal.Decimal(ps_data["amount"]) / 100
        currency = ps_data["currency"]

        if paid_amount != txn.amount or currency != txn.currency:
            return Response({"error": "Amount mismatch"}, status=400)

        # ✅ CREDIT WALLET — SAFELY
        with db_transaction.atomic():
            txn.status = "SUCCESS"
            txn.save(update_fields=["status"])

            credit_user_wallet(
                user=txn.user,
                amount=txn.amount,
                reference=txn.reference,
                source="paystack"
            )

        return Response({"status": "SUCCESS"})














# api/paystack_deposits.py (CONT.)

@csrf_exempt
def PaystackWebhookView(request):
    """
    SECURE webhook endpoint that Paystack calls automatically
    """

    signature = request.headers.get("x-paystack-signature")

    payload = request.body

    # Verify hashing signature
    hash = hmac.new(
        key=settings.PAYSTACK_SECRET_KEY.encode(),
        msg=payload,
        digestmod=hashlib.sha512
    ).hexdigest()

    if hash != signature:
        return HttpResponse(status=401)

    data = json.loads(payload.decode("utf-8"))

    ps_data = data["data"]

    if ps_data["status"] != "success":
        return HttpResponse(status=200)

    reference = ps_data["reference"]
    amount = decimal.Decimal(ps_data["amount"]) / 100
    currency = ps_data["currency"]

    try:
        txn = Transaction.objects.get(reference=reference)
    except Transaction.DoesNotExist:
        return HttpResponse(status=200)

    if txn.status == "SUCCESS":
        return HttpResponse(status=200)

    if amount != txn.amount or currency != txn.currency:
        return HttpResponse(status=400)

    # ✅ CREDIT USER WALLET
    with db_transaction.atomic():
        txn.status = "SUCCESS"
        txn.save(update_fields=["status"])

        credit_user_wallet(
            user=txn.user,
            amount=txn.amount,
            reference=txn.reference,
            source="paystack-webhook"
        )

    return HttpResponse(status=200)
