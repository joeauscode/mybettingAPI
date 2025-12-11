# api/management/commands/manage_rounds.py

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from api.models import Round, LotterySettings
from api.utils import finalize_round

ROUND_DURATION_MINUTES = 3
BREAK_DURATION_SECONDS = 30
CYCLE_KEY = "cycle_counter"


class Command(BaseCommand):
    help = "Check and manage lottery rounds"

    def handle(self, *args, **options):
        now = timezone.now()
        active_round = Round.objects.filter(is_accepting=True, is_finished=False).first()

        if active_round:
            # Round exists: check if expired
            if now >= active_round.accept_until:
                self.end_round(active_round)
            else:
                self.stdout.write(
                    f"Round #{active_round.id} still active. "
                    f"Time left: {active_round.accept_until - now}"
                )
        else:
            # No active round → check break period
            last_round = Round.objects.filter(is_finished=True).order_by("-id").first()
            if last_round:
                elapsed = (now - last_round.accept_until).total_seconds()
                if elapsed >= BREAK_DURATION_SECONDS:
                    self.start_new_round()
                else:
                    self.stdout.write(
                        f"Waiting for break to finish. {BREAK_DURATION_SECONDS - int(elapsed)} seconds left"
                    )
            else:
                # First ever round
                self.start_new_round()

    def start_new_round(self):
        now = timezone.now()
        r = Round.objects.create(
            is_accepting=True,
            is_finished=False,
            accept_until=now + timedelta(minutes=ROUND_DURATION_MINUTES),
            no_match_draws=0,
        )
        self.stdout.write(f"Started round #{r.id}, ends at {r.accept_until}")

    def end_round(self, round_obj):
        # Get current cycle counter from DB, create if missing
        setting, created = LotterySettings.objects.get_or_create(
            key=CYCLE_KEY,
            defaults={"value": 1}
        )
        cycle_counter = setting.value

        # Finalize the round using utils.py
        next_cycle = finalize_round(round_obj, cycle_counter)

        # Save updated counter back to DB
        setting.value = next_cycle
        setting.save()

        self.stdout.write(f"Ended round #{round_obj.id}, next cycle #{next_cycle}")
