from django.db import transaction
from api.models import Profile, Transaction

def credit_user_wallet(user, amount, reference=None, source=None):
    """
    Safely credit a user's profile balance.
    Ensures idempotency by checking the transaction reference.
    """
    if reference:
        # check if this transaction has already been credited
        if Transaction.objects.filter(reference=reference, status='COMPLETED').exists():
            return

    with transaction.atomic():
        # update profile balance
        profile, _ = Profile.objects.get_or_create(user=user)
        profile.balance += amount
        profile.save()

        # mark the transaction completed if reference exists
        if reference:
            txn = Transaction.objects.filter(user=user, reference=reference).first()
            if txn:
                txn.status = 'COMPLETED'
                txn.save(update_fields=['status'])
