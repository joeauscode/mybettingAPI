from datetime import timedelta
import uuid
from decimal import Decimal
import requests
from .serializers import ProfileSerializer

from django.conf import settings
from django.contrib.auth import get_user_model, authenticate
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from rest_framework import serializers, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework_simplejwt.tokens import RefreshToken

from api.models import Profile
from api.serializers import UserRegistrationSerializer
from .models import User, Profile, Round, Ticket, BankWithdrawal, Transaction
from .serializers import (
    PlayRequestSerializer,
    TicketSerializer,
    RoundStatusSerializer,
    UserRegistrationSerializer,
    UserLoginSerializer,
    ProfileSerializer
)

User = get_user_model()




# =======================================

class ProfilePictureUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        """Fetch the current user's profile data"""
        profile = request.user.profile
        serializer = ProfileSerializer(profile, context={"request": request})
        return Response(serializer.data)

    def post(self, request):
        """Update avatar and optionally bank info"""
        profile = request.user.profile
        data = request.data.copy()

        # Prevent bank info changes if already submitted
        if profile.withdrawal_info_submitted_at:
            data.pop("bank_account_number", None)
            data.pop("bank_name", None)

        serializer = ProfileSerializer(
            profile,
            data=data,
            partial=True,  # allows partial update (e.g., only avatar)
            context={"request": request}  # needed for avatar_url field
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()  # this saves the avatar and any other updated fields

        return Response({
            "message": "Profile updated successfully",
            "avatar_url": serializer.data.get("avatar_url"),
            "full_name": f"{profile.user.first_name} {profile.user.last_name}".strip(),
            "bank_account_number": serializer.data.get("bank_account_number"),
            "bank_name": serializer.data.get("bank_name")
        }, status=200)

# ======================================



class LoginUserView(APIView):
    permission_classes = []  # Allow anyone to login

    def post(self, request):
        serializer = UserLoginSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            password = serializer.validated_data['password']

            # Authenticate user using email
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                return Response({"detail": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

            user = authenticate(username=user.username, password=password)
            if user is not None:
                refresh = RefreshToken.for_user(user)
                return Response({
                    "access": str(refresh.access_token),
                    "refresh": str(refresh),
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                })
            else:
                return Response({"detail": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)







# ======================================================================================



class RegisterUserView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        print("Request data:", request.data)
        serializer = UserRegistrationSerializer(data=request.data)

        if serializer.is_valid():
            try:
                user = serializer.save()
            except IntegrityError:
                return Response({"email": "Email is already registered."}, status=400)

            profile = user.profile
            verification_link = f"http://localhost:5173/verify-email/{profile.email_verification_token}/"

            return Response({
                "message": "User registered successfully. Please verify your email.",
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "balance": float(profile.balance),
                "token": None,
                "refresh": None,
                "verification_link": verification_link
            }, status=201)

        print("Serializer errors:", serializer.errors)
        return Response(serializer.errors, status=400)




class VerifyEmailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, token):
        try:
            profile = Profile.objects.get(email_verification_token=token)
        except Profile.DoesNotExist:
            return Response({"error": "Invalid or expired token."}, status=400)

        # Check if token expired (6 hours)
        if profile.email_verification_sent_at + timedelta(hours=6) < timezone.now():
            return Response({"error": "Invalid or expired token."}, status=400)

        profile.mark_email_verified()
        user = profile.user
        refresh = RefreshToken.for_user(user)

        return Response({
            "message": "Email verified successfully.",
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "balance": float(profile.balance),
            "token": str(refresh.access_token),
            "refresh": str(refresh)
        })

# =======================================
# PLAY TICKET VIEW
# =======================================

class PlayTicketView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PlayRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        numbers = list(set(serializer.validated_data["numbers"]))
        amount = serializer.validated_data["amount"]

        if len(numbers) != 6:
            return Response(
                {"detail": "Numbers must be 6 unique values."},
                status=400
            )

        user_profile = request.user.profile

        if user_profile.balance < amount:
            return Response(
                {"detail": "Insufficient balance."},
                status=400
            )

        now = timezone.now()
        current_round = Round.objects.filter(
            is_accepting=True,
            is_finished=False,
            accept_until__gt=now
        ).first()

        if not current_round:
            return Response(
                {"detail": "No active round accepting plays at this time."},
                status=400
            )

        with transaction.atomic():
            user_profile.balance -= amount
            user_profile.save()

            ticket = Ticket.objects.create(
                round=current_round,
                user=request.user,
                numbers=sorted(numbers),
                amount=amount
            )

        return Response(
            {
                "ticket_code": ticket.ticket_code,
                "round_id": current_round.id,
                "numbers": ticket.numbers,
                "amount": ticket.amount,
                "created_at": ticket.created_at
            },
            status=201
        )

    def get(self, request, ticket_code):
        """
        Retrieve ticket details by ticket_code for printing
        """
        try:
            ticket = Ticket.objects.get(ticket_code=ticket_code, user=request.user)
        except Ticket.DoesNotExist:
            return Response(
                {"detail": "Ticket not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        return Response(
            {
                "ticket_code": ticket.ticket_code,
                "round_id": ticket.round.id,
                "numbers": ticket.numbers,
                "amount": ticket.amount,
                "created_at": ticket.created_at
            },
            status=200
        )





# =======================================
# ROUND STATUS VIEW
# =======================================




class CurrentRoundStatusView(APIView):
    permission_classes = [AllowAny] 
    """
    Returns the current active round's status.
    If no round is active, returns a 404.
    """
    def get(self, request):
        now = timezone.now()
        current_round = Round.objects.filter(
            is_accepting=True,
            is_finished=False,
            accept_until__gt=now
        ).order_by('-id').first()

        if not current_round:
            return Response({"detail": "No active round"}, status=404)

        accept_until = current_round.accept_until
        if timezone.is_naive(accept_until):
            accept_until = timezone.make_aware(accept_until, timezone.utc)

        time_left = max(int((accept_until - now).total_seconds()), 0)

        data = {
            "id": current_round.id,
            "is_accepting": current_round.is_accepting,
            "is_finished": current_round.is_finished,
            "accept_until": accept_until,
            "draw": current_round.draw or [],
            "time_left_seconds": time_left,
            "tickets_count": current_round.tickets.count()
        }
        return Response(data)


# =======================================
# TICKET DETAIL VIEW
# =======================================



class TicketDetailView(APIView):
    """
    Retrieve a single ticket by its ticket_code.
    Users search using the short, user-friendly ticket_code.
    """

    def get(self, request, ticket_code):
        try:
            ticket = Ticket.objects.get(ticket_code=ticket_code)
        except Ticket.DoesNotExist:
            return Response(
                {"detail": "Ticket not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = TicketSerializer(ticket)
        return Response(serializer.data)














# -----------------------------
# User requests a withdrawal
# -----------------------------
class RequestWithdrawalView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        amount = request.data.get("amount")

        # Validate amount
        try:
            amount = Decimal(amount)
            if amount <= 0:
                raise ValueError
        except:
            return Response({"error": "Invalid amount"}, status=400)

        profile = user.profile

        # Check if user is allowed to withdraw
        if not profile.can_withdraw():
            return Response({"error": "Withdrawal info not approved or 48h not passed"}, status=400)

        # Check user balance
        if profile.balance < amount:
            return Response({"error": "Insufficient balance"}, status=400)

        reference = str(uuid.uuid4())

        # Deduct balance and create withdrawal atomically
        with transaction.atomic():
            profile.balance -= amount
            profile.save()

            withdrawal = BankWithdrawal.objects.create(
                user=user,
                amount=amount,
                reference=reference
            )

        return Response({
            "message": "Withdrawal requested successfully",
            "reference": reference,
            "status": withdrawal.status
        })


# -----------------------------
# Admin approves withdrawal
# -----------------------------
class AdminApproveWithdrawalView(APIView):
    """
    Admin approves a withdrawal.
    Once approved, a signal can trigger Paystack payout automatically.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]

    def post(self, request, reference):
        try:
            withdrawal = BankWithdrawal.objects.get(reference=reference, status="PENDING")
        except BankWithdrawal.DoesNotExist:
            return Response({"error": "Withdrawal not found or already processed"}, status=404)

        withdrawal.status = "APPROVED"
        withdrawal.save(update_fields=["status"])

        return Response({"message": "Withdrawal approved"})


# -----------------------------
# Admin rejects withdrawal
# -----------------------------
class AdminRejectWithdrawalView(APIView):
    """
    Admin rejects a withdrawal and refunds the user balance.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]

    def post(self, request, reference):
        try:
            withdrawal = BankWithdrawal.objects.get(reference=reference, status="PENDING")
        except BankWithdrawal.DoesNotExist:
            return Response({"error": "Withdrawal not found or already processed"}, status=404)

        with transaction.atomic():
            # Refund user
            profile = withdrawal.user.profile
            profile.balance += withdrawal.amount
            profile.save()

            withdrawal.status = "REJECTED"
            withdrawal.save(update_fields=["status"])

        return Response({"message": "Withdrawal rejected and refunded"})
