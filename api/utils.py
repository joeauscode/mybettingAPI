# # api/utils.py

# import random
# from django.db import transaction
# from django.db.models import F
# from .models import Round, Ticket

# WIN_MULTIPLIER = 5        # Winning ticket multiplies the bet
# TOTAL_LOSE_ROUNDS = 5     # Number of losing rounds before a partial win
# PARTIAL_WIN_MATCH = 3     # How many numbers match for partial win

# def finalize_round(round_obj, rounds_played):
#     """
#     Finalizes a lottery round:
#     1. First TOTAL_LOSE_ROUNDS rounds: all tickets lose.
#     2. Next round: one ticket partially wins (PARTIAL_WIN_MATCH numbers).
#     3. Automatically deposits winnings to the winner's profile.

#     Args:
#         round_obj (Round): Round instance to finalize.
#         rounds_played (int): Counter tracking win/lose pattern.

#     Returns:
#         int: Updated rounds_played counter for next round.
#     """
#     # Fetch all tickets for this round (only users with profiles can play)
#     tickets = Ticket.objects.filter(round=round_obj).select_related('user__profile')

#     # Collect all numbers played in this round
#     all_numbers_played = set()
#     for ticket in tickets.values_list('numbers', flat=True):
#         all_numbers_played.update(ticket)

#     # ---------------------------
#     # Determine the draw numbers
#     # ---------------------------
#     winner_ticket = None

#     if rounds_played < TOTAL_LOSE_ROUNDS:
#         # Losing rounds: pick 6 numbers not in any ticket
#         available_numbers = set(range(1, 41)) - all_numbers_played
#         population = list(available_numbers)
#         draw = sorted(random.sample(population, 6)) if len(population) >= 6 else sorted(random.sample(range(1, 41), 6))
#     else:
#         # Winning round: pick one random ticket to partially win
#         winner_ticket = tickets.order_by('?').first()
#         draw = random.sample(range(1, 41), 6)
#         if winner_ticket:
#             draw[:PARTIAL_WIN_MATCH] = winner_ticket.numbers[:PARTIAL_WIN_MATCH]
#             draw = sorted(draw)

#     # ---------------------------
#     # Finalize the round
#     # ---------------------------
#     round_obj.draw = list(draw)
#     round_obj.is_finished = True
#     round_obj.is_accepting = False
#     round_obj.save(update_fields=['draw', 'is_finished', 'is_accepting'])

#     # ---------------------------
#     # Update tickets and balances
#     # ---------------------------
#     if winner_ticket:
#         winner_ticket.winning = True
#         winner_ticket.win_amount = winner_ticket.amount * WIN_MULTIPLIER
#         winner_ticket.save(update_fields=['winning', 'win_amount'])

#         # Safely credit user's profile within a transaction
#         profile = winner_ticket.user.profile
#         with transaction.atomic():
#             profile.balance = F('balance') + winner_ticket.win_amount
#             profile.save(update_fields=['balance'])

#     # Mark all other tickets as lost
#     tickets.exclude(id=winner_ticket.id if winner_ticket else None).update(winning=False, win_amount=0)

#     # ---------------------------
#     # Update rounds_played counter
#     # ---------------------------
#     rounds_played += 1
#     if rounds_played > TOTAL_LOSE_ROUNDS:
#         rounds_played = 1  # restart at 1 instead of 0

#     return rounds_played











# api/utils.py

import random
from django.db import transaction
from django.db.models import F
from .models import Round, Ticket

# Updated multipliers
WIN_MULTIPLIER_MAP = {
    3: 5,   # 3 numbers match → ×5
    4: 7,   # 4 numbers match → ×7
    5: 15,  # 5 numbers match → ×15
    6: 50   # 6 numbers match → ×50
}

TOTAL_LOSE_ROUNDS = 5
PARTIAL_WIN_MATCH = 3  # First 3 numbers of the winner ticket will match

def finalize_round(round_obj, rounds_played):
    tickets = Ticket.objects.filter(round=round_obj).select_related('user__profile')

    # Collect all numbers played
    all_numbers_played = set()
    for ticket in tickets.values_list('numbers', flat=True):
        all_numbers_played.update(ticket)

    winner_ticket = None

    if rounds_played < TOTAL_LOSE_ROUNDS:
        # Losing rounds: pick 6 numbers not in any ticket
        available_numbers = set(range(1, 41)) - all_numbers_played
        population = list(available_numbers)
        draw = sorted(random.sample(population, 6)) if len(population) >= 6 else sorted(random.sample(range(1, 41), 6))
    else:
        # Winning round: pick one random ticket to win partially
        winner_ticket = tickets.order_by('?').first()
        draw = random.sample(range(1, 41), 6)
        if winner_ticket:
            # Ensure first PARTIAL_WIN_MATCH numbers match
            draw[:PARTIAL_WIN_MATCH] = winner_ticket.numbers[:PARTIAL_WIN_MATCH]
            draw = sorted(draw)

    # Save draw and close round
    round_obj.draw = list(draw)
    round_obj.is_finished = True
    round_obj.is_accepting = False
    round_obj.save(update_fields=['draw', 'is_finished', 'is_accepting'])

    # ---------------------------
    # Update tickets and balances
    # ---------------------------
    if winner_ticket:
        matched_numbers = len(set(winner_ticket.numbers) & set(draw))
        multiplier = WIN_MULTIPLIER_MAP.get(matched_numbers, 0)  # 0 if <3 matches

        winner_ticket.winning = matched_numbers >= 3
        winner_ticket.win_amount = winner_ticket.amount * multiplier if winner_ticket.winning else 0
        winner_ticket.save(update_fields=['winning', 'win_amount'])

        if winner_ticket.winning:
            profile = winner_ticket.user.profile
            with transaction.atomic():
                profile.balance = F('balance') + winner_ticket.win_amount
                profile.save(update_fields=['balance'])

    # All other tickets lose
    tickets.exclude(id=winner_ticket.id if winner_ticket else None).update(winning=False, win_amount=0)

    # ---------------------------
    # Update rounds_played counter
    rounds_played += 1
    if rounds_played > TOTAL_LOSE_ROUNDS:
        rounds_played = 1

    return rounds_played

