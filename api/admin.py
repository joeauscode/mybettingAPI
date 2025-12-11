from django.contrib import admin
from .models import Profile, Transaction, Round, Ticket, BankWithdrawal



@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'balance', 'withdrawal_info_approved', 'withdrawal_info_submitted_at', 'withdrawal_info_approved_at')
    readonly_fields = ('withdrawal_info_submitted_at', 'withdrawal_info_approved_at')
    actions = ['approve_withdrawal_info']

    def approve_withdrawal_info(self, request, queryset):
        for profile in queryset:
            profile.approve_withdrawal_info()
        self.message_user(request, "Selected profiles have been approved.")
    approve_withdrawal_info.short_description = "Approve selected withdrawal info"
    





@admin.register(BankWithdrawal)
class BankWithdrawalAdmin(admin.ModelAdmin):
    list_display = ("user", "amount", "status", "reference", "created_at")
    list_filter = ("status",)
    actions = ["approve_withdrawals"]

    def approve_withdrawals(self, request, queryset):
        for withdrawal in queryset.filter(status="PENDING"):
            withdrawal.status = "APPROVED"
            withdrawal.save()
    approve_withdrawals.short_description = "Approve selected withdrawals"




admin.site.register(Transaction)
admin.site.register(Round)
admin.site.register(Ticket)

