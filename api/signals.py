from django.db.models.signals import post_save
from django.dispatch import receiver
import requests
import decimal
from django.conf import settings
from .models import *

@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)










PAYSTACK_BASE = "https://api.paystack.co"
PAYSTACK_SECRET = settings.PAYSTACK_SECRET_KEY

def paystack_headers():
    return {
        "Authorization": f"Bearer {PAYSTACK_SECRET}",
        "Content-Type": "application/json",
    }

@receiver(post_save, sender=BankWithdrawal)
def payout_on_approval(sender, instance, created, **kwargs):
    """
    Automatically trigger Paystack payout when admin approves a withdrawal.
    """
    # Only trigger if status changed to APPROVED
    if not created and instance.status == "APPROVED":
        # Skip if already completed
        if getattr(instance, "_payout_triggered", False) or instance.status == "COMPLETED":
            return

        setattr(instance, "_payout_triggered", True)  # Prevent double trigger

        account_details = instance.details
        if not account_details:
            print(f"No account details for withdrawal {instance.reference}")
            return

        recipient_code = account_details.get("recipient_code")
        if not recipient_code:
            print(f"No recipient_code for withdrawal {instance.reference}")
            return

        amount_kobo = int(decimal.Decimal(instance.amount) * 100)
        payload = {
            "source": "balance",
            "amount": amount_kobo,
            "recipient": recipient_code,
            "reason": f"Payout for withdrawal {instance.reference}",
            "reference": instance.reference,
        }

        try:
            resp = requests.post(f"{PAYSTACK_BASE}/transfer", headers=paystack_headers(), json=payload, timeout=15)
            data = resp.json()
        except Exception as e:
            print(f"Paystack transfer failed: {e}")
            instance.status = "FAILED"
            instance.save(update_fields=["status"])
            return

        if data.get("status") and data.get("data"):
            instance.status = "COMPLETED"
            instance.save(update_fields=["status"])
            print(f"Withdrawal {instance.reference} payout completed.")
        else:
            instance.status = "FAILED"
            instance.save(update_fields=["status"])
            print(f"Paystack transfer response error: {data}")
