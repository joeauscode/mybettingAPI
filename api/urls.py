from django.urls import path
from .views import (
    PlayTicketView,
    CurrentRoundStatusView,
    ProfilePictureUploadView,
    TicketDetailView,
    LoginUserView,
    RegisterUserView,
    VerifyEmailView,

)
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .flutterwave_deposits import DepositView, FlutterwaveWebhookView, FlutterwaveVerifyView


from .paystack_deposits import (
    PaystackDepositView,
    PaystackVerifyView,
    PaystackWebhookView,
)


urlpatterns = [
    path("register/", RegisterUserView.as_view(), name="register"),
    path("verify-email/<str:token>/", VerifyEmailView.as_view(), name="verify_email"),
    path("play/", PlayTicketView.as_view(), name="play"),
    path("rounds/current/", CurrentRoundStatusView.as_view(), name="current_round"),
    path("profile/picture/", ProfilePictureUploadView.as_view(), name="profile_picture"),
    path("tickets/<uuid:ticket_uuid>/", TicketDetailView.as_view(), name="ticket_detail"),
    path('login/', LoginUserView.as_view(), name='login'),
 

    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    path("api/deposit/", DepositView.as_view(), name="deposit"),
    path("api/flutterwave/webhook/", FlutterwaveWebhookView.as_view(), name="flutterwave-webhook"),
    path("api/flutterwave/verify/", FlutterwaveVerifyView.as_view(), name="flutterwave-verify"),
    
    
    # paystack
    path("api/paystack/deposit/", PaystackDepositView.as_view()),
    path("api/paystack/verify/", PaystackVerifyView.as_view()),
    path("api/paystack/webhook/", PaystackWebhookView),
]








