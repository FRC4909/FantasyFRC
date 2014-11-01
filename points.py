import logging
from alliance_management import get_team_schedule
from datastore_classes import Team_Event, team_event_key, team_key
from progress_through_elimination_classification import UNDETERMINED, DIDNTQUALIFY, QUARTERFINALIST, SEMIFINALIST, FINALIST, WINNER
"""Uses point system described in http://www.chiefdelphi.com/media/papers/2574"""

points_per_qual_win = 2
points_per_qual_tie = 1
points_per_qual_loss = 0

elemination_progress_points = {
    UNDETERMINED: 0,
    DIDNTQUALIFY: 0,
    QUARTERFINALIST: 4,
    SEMIFINALIST: 10,
    FINALIST: 20,
    WINNER: 30
}

humman_readable_point_categories = [
    "Matches won in qualification", 
    "Matches tied in qualification", 
    "Matches lost in qualification", 
    "Progress in elemination", 
    "Seed",  
    "Awards"
]

explanation_of_point_categories = [
    "Every match won in the qualification rounds earns a team 2 points",
    "Every match lost in the qualification rounds earns a team 1 point",
    "Teams get no points for matches lost during the qualification rounds",
    "Teams get points for their progress through elemination rounds as follows: Quarterfinalist: 4, Semifinalist: 10, Finalist: 20, Winner: 30",
    "Teams seeded 1st get 20, 2nd-3rd get 12, 4th-8th get 6, 9th-12th get 3, 13th-16th get 2",
    "Awards are assigned points based off this document"
]

points_for_seed_1 = 20
points_for_seed_2to3 = 12
points_for_seed_4to8 = 6
points_for_seed_9to12 = 3
points_for_seed_13to16 = 2

def get_seed_points(seed):
    if seed == 1:
        return points_for_seed_1
    elif seed >= 2 and seed <= 3:
        return points_for_seed_2to3
    elif seed >= 4 and seed <= 8:
        return points_for_seed_4to8
    elif seed >= 9 and seed <= 12:
        return points_for_seed_9to12
    elif seed >= 13 and seed <= 16:
        return points_for_seed_13to16
    else:
        return 0

'''
Returns a list of point values that are orderered as described by the humman_readable_point_categories variable
'''
def get_point_breakdown_for_event(team_number, event_id):
    team_event = Team_Event.get_or_insert(team_event_key(team_key(str(team_number)), event_id).id(), parent=team_key(str(team_number)))
    
    # Defualt values if event doesn't exist
    qual_win_points = 0
    qual_tie_points = 0
    qual_loss_points = 0
    elimination_points = 0
    seed_points = 0
    award_points = 0

    if team_event.win: #For debug purposes, so unloaded events don't raise exceptions
        qual_win_points = team_event.win * points_per_qual_win
        qual_tie_points = team_event.tie * points_per_qual_tie
        qual_loss_points = team_event.loss * points_per_qual_loss
        elimination_points = elemination_progress_points[team_event.elimination_progress]
        seed_points = get_seed_points(team_event.rank)
        award_points = 0
        for award in team_event.awards:
            if award != 1 and award != 2: #Don't give double points for winners/finalists
                award_points += award_points_by_TBA_id[award]

    breakdown = [
        qual_win_points, 
        qual_tie_points, 
        qual_loss_points, 
        elimination_points, 
        seed_points, 
        award_points
        ]
    return breakdown

def get_team_points_at_event(team_number, event_id):
    breakdown = get_point_breakdown_for_event(team_number, event_id)
    return sum(breakdown)

def get_points_to_date(team_number):
    schedule = get_team_schedule(team_number)
    points = 0
    for week, event in enumerate(schedule):
        if schedule[week]['competition_name'] != "":

            event_key = schedule[week]['event_key']
            points = points + get_team_points_at_event(team_number, event_key)
    return points


#Uses ids based off of https://github.com/the-blue-alliance/the-blue-alliance/blob/master/consts/award_type.py
award_points_by_TBA_id = {
    0 : 42,
    1 : 30,
    2 : 20,

    3 : 8,
    4 : 4,
    5 : 2,
    6 : 2,
    7 : 2,
    8 : 2,

    9 : 36,
    10 : 20,
    11 : 2,
    12 : 2,
    13 : 5,
    14 : 5,
    15 : 15,
    16 : 15,
    17 : 15,
    18 : 2,
    19 : 2,
    20 : 15,
    21 : 15,
    22 : 2,
    23 : 15,
    24 : 15,
    25 : 2,
    26 : 2,
    27 : 2,
    28 : 2,
    29 : 15,
    30 : 2,
    31 : 2,
    32 : 2,
    33 : 2,
    34 : 2,
    35 : 2,
    36 : 2,
    37 : 2,
    38 : 15,
    39 : 2,
    40 : 2,
    41 : 2,
    42 : 2,
    43 : 2,
    44 : 2,
    45 : 2,
    46 : 2,
    47 : 2,
    48 : 2,
    49 : 2,
    50 : 2,
    51 : 2,
    52 : 2,
    53 : 2,
    54 : 2,
    55 : 2,
    56 : 2,
    57 : 2,
    58 : 2,
    59 : 5,
    60 : 2,
    61 : 2,
    62 : 2,
    63 : 2,
    64 : 15,
    65 : 2,
    66 : 42, #I consider golden corn dog to be equivalent to chairman's
}