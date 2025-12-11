from django.db import models, transaction
from django.contrib.auth.models import User
import uuid
import secrets
from datetime import timedelta
import string
from django.utils import timezone
from django.db import models





# ======================================


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True, default="avatars/Avatar_Aang.png")

    # Bank info
    bank_account_number = models.CharField(max_length=20, blank=True, null=True)
    bank_name = models.CharField(max_length=100, blank=True, null=True)

    # Email verification
    is_email_verified = models.BooleanField(default=False)
    email_verification_token = models.CharField(max_length=100, blank=True, null=True)
    email_verification_sent_at = models.DateTimeField(blank=True, null=True)

    # Withdrawal workflow
    withdrawal_info_submitted_at = models.DateTimeField(blank=True, null=True)
    withdrawal_info_approved = models.BooleanField(default=False)
    withdrawal_info_approved_at = models.DateTimeField(blank=True, null=True)

    # ------------------------------
    # Bank info / withdrawal methods
    # ------------------------------

    def submit_bank_info(self, bank_account_number, bank_name):
        """Submit bank info once only."""
        if self.withdrawal_info_submitted_at:
            raise ValueError("Bank info already submitted")
        
        # Use user's full name as bank account name
        account_name = f"{self.user.first_name} {self.user.last_name}".strip()
        
        self.bank_account_number = bank_account_number
        self.bank_name = bank_name
        self.withdrawal_info_submitted_at = timezone.now()
        self.withdrawal_info_approved = False
        self.withdrawal_info_approved_at = None
        self.save()

    def can_withdraw(self):
        """Check if withdrawal is allowed."""
        if not self.withdrawal_info_approved or not self.withdrawal_info_submitted_at:
            return False
        elapsed = timezone.now() - self.withdrawal_info_submitted_at
        return elapsed.total_seconds() >= 48 * 3600

    def withdraw(self, amount):
        """Withdraw using saved bank info."""
        if not self.can_withdraw():
            raise ValueError("Cannot withdraw yet")
        if amount > self.balance:
            raise ValueError("Insufficient balance")
        if not (self.user.first_name and self.user.last_name and self.bank_account_number and self.bank_name):
            raise ValueError("Bank info incomplete")
        self.balance -= amount
        self.save()
        # Optionally: trigger actual bank transfer here using saved info
        return {
            "account_name": f"{self.user.first_name} {self.user.last_name}".strip(),
            "bank_account_number": self.bank_account_number,
            "bank_name": self.bank_name,
            "amount": amount
        }

    def add_funds(self, amount):
        if amount <= 0:
            raise ValueError("Amount must be positive")
        self.balance += amount
        self.save()

    # ------------------------------
    # Email verification (unchanged)
    # ------------------------------

    def token_is_valid(self):
        if not self.email_verification_token or not self.email_verification_sent_at:
            return False
        expiry_time = self.email_verification_sent_at + timedelta(hours=6)
        return timezone.now() <= expiry_time

    def mark_email_verified(self):
        self.is_email_verified = True
        self.email_verification_token = None
        self.save()

    # ------------------------------
    # String representation
    # ------------------------------

    def __str__(self):
        return f"{self.user.username} - {self.balance}"

# =====================================================================

class LotterySettings(models.Model):
    key = models.CharField(max_length=50, unique=True)
    value = models.IntegerField(default=1)

    def __str__(self):
        return f"{self.key}: {self.value}"



class BankWithdrawal(models.Model):
    
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
        ("COMPLETED", "Completed"),
        ("FAILED", "Failed"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="bank_withdrawals")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="PENDING")
    reference = models.CharField(max_length=100, unique=True, default=uuid.uuid4)

    details = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.details:
            profile = self.user.profile
            self.details = {
                "account_name": f"{profile.user.first_name} {profile.user.last_name}".strip(),
                "bank_account_number": profile.bank_account_number,
                "bank_name": profile.bank_name,
            }
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} - {self.amount} - {self.status}"











# =========================================================
# ========================================================



class Transaction(models.Model):
    TRANSACTION_METHODS = [
        ('USDT', 'USDT'),
        ('BANK', 'Bank Transfer'),
    ]
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=10, choices=TRANSACTION_METHODS)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    reference = models.CharField(max_length=100, unique=True)  # unique txn id

    def __str__(self):
        return f"{self.user.username} - {self.method} - {self.amount} - {self.status}"



class Round(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    is_accepting = models.BooleanField(default=True)
    is_finished = models.BooleanField(default=False)
    accept_until = models.DateTimeField(null=True, blank=True)
    draw = models.JSONField(null=True, blank=True)  
    no_match_draws = models.IntegerField(default=0)  

    def __str__(self):
        return f"Round {self.id} - {'Accepting' if self.is_accepting else 'Closed'}"











def generate_ticket_code_for_default():
    """Simple random code for migrations (does not query DB)."""
    chars = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(8))

def generate_unique_ticket_code():
    """
    Production-safe generator that checks DB for uniqueness.
    Call this only when creating new Ticket objects, not at migration time.
    """
    chars = string.ascii_uppercase + string.digits
    while True:
        code = ''.join(secrets.choice(chars) for _ in range(8))
        # Only check DB if table exists
        try:
            if not Ticket.objects.filter(ticket_code=code).exists():
                return code
        except:
            # Table might not exist during migration
            return code


class Ticket(models.Model):
    ticket_code = models.CharField(
        max_length=8,
        unique=True,
        default=generate_ticket_code_for_default,  # safe for migrations
        db_index=True
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="tickets")
    round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name="tickets")
    numbers = models.JSONField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    winning = models.BooleanField(default=False)
    win_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.ticket_code:
            self.ticket_code = generate_unique_ticket_code()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Ticket {self.ticket_code} - User {self.user.username} - Amount {self.amount}"








    
    
    

