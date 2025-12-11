import uuid

from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.models import User

from rest_framework import serializers

from .models import Profile, Ticket, Round
from api.models import Profile  






# ================================================================
# login

class UserLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

# =====================================================================

class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = User
        fields = ["email", "first_name", "last_name", "password"]

    def create(self, validated_data):
        email = validated_data["email"]
        password = validated_data.pop("password")

        # Use email as username
        user = User(username=email, **validated_data)
        user.set_password(password)
        user.save()

        # Ensure profile exists
        profile, created = Profile.objects.get_or_create(user=user, defaults={'balance': 0})

        # Generate a fresh email verification token
        token = str(uuid.uuid4())
        profile.email_verification_token = token
        profile.email_verification_sent_at = timezone.now()
        profile.is_email_verified = False
        profile.save()

        # Send verification email
        verification_link = f"http://localhost:5173/verify-email/{token}/"
        send_mail(
            "Verify your email",
            f"Click the link to verify your account: {verification_link}",
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )

        return user

# ============================================================


class ProfileSerializer(serializers.ModelSerializer):
    # User-related fields
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)

    # Full name for bank account
    full_name = serializers.SerializerMethodField()

    # Full URL for avatar
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "balance",
            "avatar",        
            "avatar_url",
            "bank_account_number",
            "bank_name",
            "withdrawal_info_submitted_at",
            "withdrawal_info_approved",
            "withdrawal_info_approved_at",
        ]
        read_only_fields = [
            "balance",
            "withdrawal_info_submitted_at",
            "withdrawal_info_approved",
            "withdrawal_info_approved_at",
            "full_name",
        ]

    def get_full_name(self, obj):
        return f"{obj.user.first_name} {obj.user.last_name}".strip()

    def get_avatar_url(self, obj):
        request = self.context.get("request")
        if obj.avatar:
            if request:
                return request.build_absolute_uri(obj.avatar.url)
            return obj.avatar.url
        return None

# ==============================================================


class TicketSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ticket
        fields = (
            "ticket_code",  
            "round",
            "numbers",
            "amount",
            "created_at",
            "winning",
            "win_amount"
        )
        read_only_fields = (
            "ticket_code",  
            "created_at",
            "winning",
            "win_amount"
        )


class PlayRequestSerializer(serializers.Serializer):
    numbers = serializers.ListField(
        child=serializers.IntegerField(min_value=1, max_value=90), 
        min_length=6, 
        max_length=6
    )
    amount = serializers.IntegerField(min_value=1)




    

class RoundStatusSerializer(serializers.ModelSerializer):
    time_left_seconds = serializers.SerializerMethodField()
    tickets_count = serializers.SerializerMethodField()

    class Meta:
        model = Round
        fields = ("id", "is_accepting", "is_finished", "accept_until", "draw", "time_left_seconds", "tickets_count")

    def get_time_left_seconds(self, obj):
        from django.utils import timezone
        if not obj.accept_until or not obj.is_accepting:
            return 0
        delta = obj.accept_until - timezone.now()
        return max(int(delta.total_seconds()), 0)

    def get_tickets_count(self, obj):
        return obj.tickets.count()
