# views/flutterwave_deposits.py
import uuid
import decimal
import requests
from django.conf import settings
from django.db import transaction as db_transaction
from django.http import HttpResponse, JsonResponse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response

from django.shortcuts import get_object_or_404


from .models import Transaction        
from .wallet import credit_user_wallet  


FLUTTERWAVE_BASE = getattr(settings, "FLUTTERWAVE_BASE_URL", "https://api.flutterwave.com/v3")
FLUTTERWAVE_SECRET_KEY = settings.FLUTTERWAVE_SECRET_KEY
FLUTTERWAVE_WEBHOOK_SECRET = getattr(settings, "FLUTTERWAVE_WEBHOOK_SECRET", None)


def _float_from_amount(value):
    try:
        # Accept str/"100", Decimal, float
        return float(decimal.Decimal(str(value)))
    except Exception:
        return None


def _flutterwave_headers():
    return {
        "Authorization": f"Bearer {FLUTTERWAVE_SECRET_KEY}",
        "Content-Type": "application/json"
    }


class DepositView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        raw_amount = request.data.get("amount")
        method = request.data.get("method", "").upper()

        amount = _float_from_amount(raw_amount)
        if amount is None or amount <= 0:
            return Response({"error": "Invalid amount"}, status=status.HTTP_400_BAD_REQUEST)

        if method not in ("USDT", "BANK"):
            return Response({"error": "Invalid payment method; use 'USDT' or 'BANK'."},
                            status=status.HTTP_400_BAD_REQUEST)

        # Generate unique reference
        reference = str(uuid.uuid4())

        # Create pending transaction in DB
        txn = Transaction.objects.create(
            user=user,
            amount=decimal.Decimal(str(amount)),
            currency="NGN" if method == "BANK" else "USDT",
            payment_method=method,
            status="PENDING",
            reference=reference
        )

        if method == "BANK":
            # Build flutterwave payload (payment link)
            payload = {
                "tx_ref": reference,
                "amount": str(amount),
                "currency": "NGN",
                # allow common options; frontend may redirect to payment-callback to verify
                "payment_options": "card,banktransfer",
                "redirect_url": request.data.get("redirect_url") or "https://yourfrontend.com/payment-callback/",
                "customer": {
                    "email": user.email,
                    "name": f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip() or user.username
                },
                "customizations": {
                    "title": "Wallet Deposit",
                    "description": f"Deposit for user {user.id}"
                }
            }

            try:
                resp = requests.post(f"{FLUTTERWAVE_BASE}/payments", json=payload, headers=_flutterwave_headers(), timeout=15)
            except requests.RequestException as exc:
                # network / timeout
                txn.status = "FAILED"
                txn.save(update_fields=["status"])
                return Response({"detail": "Failed to contact payment gateway", "error": str(exc)},
                                status=status.HTTP_502_BAD_GATEWAY)

            try:
                data = resp.json()
            except Exception:
                txn.status = "FAILED"
                txn.save(update_fields=["status"])
                return Response({"detail": "Invalid response from payment gateway"}, status=status.HTTP_502_BAD_GATEWAY)

            # Flutterwave returns top-level "status" (success) and nested data
            if data.get("status") != "success" or "data" not in data:
                txn.status = "FAILED"
                txn.save(update_fields=["status"])
                return Response({"detail": "Failed to create payment", "response": data}, status=status.HTTP_400_BAD_REQUEST)

            fw_data = data["data"]
            payment_link = fw_data.get("link")
            fw_payment_id = fw_data.get("id")  # store this to use verify endpoint

            # Save flutterwave_payment_id for later verification
            txn.flutterwave_payment_id = fw_payment_id
            txn.save(update_fields=["flutterwave_payment_id"])

            payment_info = {"payment_link": payment_link, "flutterwave_payment_id": fw_payment_id}

        else:  # USDT
            # SMALL: placeholder – in production use a real crypto payments provider (Coinbase Commerce, NOWPayments, etc.)
            # For demo, we return an address/invoice note and mark transaction still pending until verified on-chain.
            # You must implement on-chain watching or provider webhooks to mark SUCCESS.
            usdt_address = settings.USDT_RECEIVE_ADDRESS if hasattr(settings, "USDT_RECEIVE_ADDRESS") else "your_USDT_address_here"
            payment_info = {"USDT_address": usdt_address}
            # keep txn pending until you confirm on-chain

        return Response({
            "message": "Transaction initiated",
            "transaction_id": txn.id,
            "reference": reference,
            "status": txn.status,
            **payment_info
        }, status=status.HTTP_201_CREATED)


class FlutterwaveVerifyView(APIView):
    """
    Call this from your frontend redirect (payment-callback) to verify the transaction server-side.
    The frontend should send the tx_ref or the flutterwave payment id (if available).
    """

    def post(self, request):
        tx_ref = request.data.get("tx_ref")
        fw_payment_id = request.data.get("flutterwave_payment_id")  # optional

        if not tx_ref and not fw_payment_id:
            return Response({"error": "tx_ref or flutterwave_payment_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Find the transaction
        try:
            txn = Transaction.objects.get(reference=tx_ref) if tx_ref else Transaction.objects.get(flutterwave_payment_id=str(fw_payment_id))
        except Transaction.DoesNotExist:
            return Response({"error": "Transaction not found"}, status=status.HTTP_404_NOT_FOUND)

        # If already successful, return early
        if txn.status == "SUCCESS":
            return Response({"status": "SUCCESS", "transaction_id": txn.id})

        # Prefer verifying by flutterwave_payment_id if we have it
        if txn.flutterwave_payment_id:
            verify_url = f"{FLUTTERWAVE_BASE}/transactions/{txn.flutterwave_payment_id}/verify"
        else:
            # Fallback: try verifying by tx_ref via a search endpoint - here we call transactions? reference endpoint if available
            # Many Flutterwave flows include the transaction id in callback; if not available, you should use the tx_ref to find it.
            verify_url = f"{FLUTTERWAVE_BASE}/transactions/verify_by_reference?tx_ref={txn.reference}"

        try:
            resp = requests.get(verify_url, headers=_flutterwave_headers(), timeout=10)
            verify_data = resp.json()
        except requests.RequestException as exc:
            return Response({"error": "Failed to contact payment gateway", "details": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        except Exception:
            return Response({"error": "Invalid response from payment gateway"}, status=status.HTTP_502_BAD_GATEWAY)

        # Example successful shape: {"status":"success","data":{...}} - adjust if your gateway differs
        if verify_data.get("status") != "success":
            return Response({"status": "FAILED", "detail": verify_data}, status=status.HTTP_400_BAD_REQUEST)

        fw_tx = verify_data.get("data", {})
        fw_status = fw_tx.get("status") or fw_tx.get("transaction_status") or fw_tx.get("payment_status")
        fw_amount = fw_tx.get("amount") or fw_tx.get("charged_amount") or fw_tx.get("amount_settled")
        fw_currency = fw_tx.get("currency")

        # Only accept definitive successful statuses; different integrations may use 'successful' or 'success'
        if str(fw_status).lower() not in ("successful", "success", "completed"):
            return Response({"status": "NOT_SUCCESS", "gateway_status": fw_status, "detail": fw_tx}, status=status.HTTP_400_BAD_REQUEST)

        # Validate amount + currency
        try:
            fw_amount_val = float(fw_amount)
        except Exception:
            return Response({"error": "Invalid amount from gateway", "gateway_response": fw_tx}, status=status.HTTP_400_BAD_REQUEST)

        if float(txn.amount) != float(fw_amount_val) or (fw_currency and txn.currency and fw_currency != txn.currency):
            # mismatch — investigation required
            return Response({"error": "Amount or currency mismatch", "expected": {"amount": str(txn.amount), "currency": txn.currency},
                             "gateway": {"amount": fw_amount, "currency": fw_currency}}, status=status.HTTP_400_BAD_REQUEST)

        # All good: mark transaction successful and credit wallet safely inside transaction
        with db_transaction.atomic():
            txn.status = "SUCCESS"
            txn.save(update_fields=["status"])
            # credit user's wallet / balance — implement this in your app
            credit_user_wallet(txn.user, txn.amount, reference=txn.reference, source="flutterwave")

        return Response({"status": "SUCCESS", "transaction_id": txn.id})


class FlutterwaveWebhookView(APIView):
    """
    Endpoint to receive Flutterwave webhooks.
    Must be configured in your Flutterwave dashboard.
    NOTE: For security verify the verif-hash header (or whatever Flutterwave sends).
    Adjust the verification method to match Flutterwave's docs if they use an HMAC or SHA signature.
    """

    # Disable DRF auth for webhook (webhooks are signed instead)
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        # Basic shared-secret header validation. Replace/upgrade this according to Flutterwave docs.
        signature = request.headers.get("verif-hash") or request.META.get("HTTP_VERIF_HASH")
        if not signature or not FLUTTERWAVE_WEBHOOK_SECRET:
            return HttpResponse(status=401)

        # If your webhook secret is a simple equality use this; otherwise compute HMAC as required by your provider docs.
        if signature != FLUTTERWAVE_WEBHOOK_SECRET:
            return HttpResponse(status=401)

        payload = request.data or {}

        # Some providers send "event" field, some send nested "data". We normalize.
        event = payload.get("event") or payload.get("event_type") or None
        data = payload.get("data") or {}

        # Only act on completed/successful charge events
        # Accept multiple naming variants
        event_type_ok = (event is None) or (str(event).lower() in ("charge.completed", "charge.successful", "transaction.completed", "transaction.successful"))
        if not event_type_ok:
            # ignore other events gracefully
            return HttpResponse(status=200)

        # Extract tx_ref and other fields from data
        tx_ref = data.get("tx_ref") or data.get("meta", {}).get("tx_ref")
        fw_payment_id = data.get("id") or data.get("tx_id")
        fw_status = data.get("status") or data.get("transaction_status")
        fw_amount = data.get("amount")
        fw_currency = data.get("currency")

        if not tx_ref:
            # can't reconcile without reference — ignore but respond 200 to avoid retries
            return HttpResponse(status=200)

        # Load transaction
        try:
            txn = Transaction.objects.get(reference=tx_ref)
        except Transaction.DoesNotExist:
            # unknown reference — ignore
            return HttpResponse(status=200)

        # If already completed, no-op
        if txn.status == "SUCCESS":
            return HttpResponse(status=200)

        # Only mark success if gateway says successful
        if str(fw_status).lower() not in ("successful", "success", "completed"):
            # not a success event
            return HttpResponse(status=200)

        # Validate amount & currency
        try:
            fw_amount_val = float(fw_amount)
        except Exception:
            # invalid numeric amount — ignore and let manual review
            return HttpResponse(status=400)

        if float(txn.amount) != float(fw_amount_val) or (fw_currency and txn.currency and fw_currency != txn.currency):
            # mismatch — log/investigate; for now return 400 so provider may retry or you can inspect logs
            return HttpResponse(status=400)

        # Everything checks out — credit the user inside DB transaction
        with db_transaction.atomic():
            txn.status = "SUCCESS"
            if fw_payment_id and not txn.flutterwave_payment_id:
                txn.flutterwave_payment_id = fw_payment_id
            txn.save(update_fields=["status", "flutterwave_payment_id"])
            # credit user's wallet
            credit_user_wallet(txn.user, txn.amount, reference=txn.reference, source="flutterwave")

        return HttpResponse(status=200)
