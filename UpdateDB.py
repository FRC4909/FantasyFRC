#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import os
import math
import random
from datetime import date, timedelta
import logging
from decimal import Decimal
import globals

from award_classification import AwardType

from google.appengine.ext.webapp.util import run_wsgi_app
from progress_through_elimination_classification import convert_TBA_level_to_progress, FINALIST, WINNER, DIDNTQUALIFY
from datastore_classes import RootEvent, root_event_key, TeamEvent, team_event_key, team_key, root_team_key, RootTeam, League, Account, Choice, Lineup, DraftPick
import time
from points import get_points_to_date
from league_management import run_week_begin, finish_week

import jinja2
import webapp2
import json

JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)

from customMechanize import _mechanize


def update_total_points():
    query = RootTeam.query()
    teams = query.fetch()
    for team in teams:
        team.total_points = get_points_to_date(team.key.id())
        team.put()

def get_unique_location(lat, lon):
    seperation = 0.001
    newlat = lat
    newlon = lon
    datastore_lat_lon = str(lat) + "," + str(lon)
    query = RootTeam.query().filter(RootTeam.latlon == datastore_lat_lon)
    results = query.fetch(1)
    if len(results) != 0:
        dir = random.randint(0, 3)
        if dir == 0:
            newlat = lat - seperation
        elif dir == 1:
            newlat = lat + seperation
        elif dir == 2:
            newlon = lon - seperation
        elif dir == 3:
            newlon = lon + seperation
        return get_unique_location(newlat, newlon)
    else:
        return str(newlat) + "," + str(newlon)

def geocode_within_limit():
    teams = RootTeam.query().fetch()
    num_this_second = 0
    this_second = time.gmtime()

    for team in teams:
        if num_this_second < 5:
            team.latlon = geocode(team.address)
            team.put()
            num_this_second += 1
        else:
            while this_second >= time.gmtime():
                time.sleep(0.1)
            num_this_second = 0
            this_second = time.gmtime()
            team.latlon = geocode(team.address)
            team.put()


def geocode(address):
    response = get_data_from_web(globals.gecode_url, address)
    if response['status'] == "OK":
        return get_unique_location(response['results'][0]['geometry']['location']['lat'],
                                   response['results'][0]['geometry']['location']['lng']
                                   )
    else:
        return ""


def get_data_from_web(url, selector, second_selector=None):
    """Gets data from the blue alliance about matches"""
    br = _mechanize.Browser()
    br.addheaders = [('X-TBA-App-Id', globals.app_id)]
    br.set_handle_robots(False)
    final_url = url.format(selector, second_selector)
    final_url = final_url.replace(' ', "%20")
    page_data = br.open(final_url, timeout=globals.mechanize_timeout).read()
    return json.loads(page_data)

def proccess_elimination_progress(match_data, alliance_data):
    team_list = []
    alliance_list = []
    for i, alliance in enumerate(alliance_data):
        teams = alliance['picks']
        for team in teams:
            team_list.append(team[3:])
            alliance_list.append(i+1)  # +1 for conversion to 1-based index
    alliance_dictionary = dict(zip(team_list,alliance_list))
    alliance_progress_levels = []

    if len(match_data) != 0:
        event_id = match_data[0]['event_key'] #0 is arbitrary, all elements should be the same
        team_list = globals.get_team_list_per_event(event_id)
        for alliance in alliance_data:
            alliance_progress_level = 0
            for match in match_data:
                for team_number_with_frc in alliance['picks']:
                    on_blue_alliance = team_number_with_frc in match['alliances']['blue']['teams']
                    on_red_alliance = team_number_with_frc in match['alliances']['red']['teams']
                    if on_blue_alliance or on_red_alliance:
                        level =  match['comp_level']
                        new_progress_level = convert_TBA_level_to_progress[level]
                        if new_progress_level > alliance_progress_level:
                            alliance_progress_level = new_progress_level
            #Now alliance progress level is correct
            alliance_progress_levels.append(alliance_progress_level)  # We add it to the list

        for team in team_list:
            if str(team) in alliance_dictionary:
                team_progress_level = alliance_progress_levels[int(alliance_dictionary[str(team)])-1]  # -1 for conversion to 0-based index
            else:
                team_progress_level = DIDNTQUALIFY

            team_event = TeamEvent.get_or_insert(team_event_key(team_key(team), event_id).id(), parent=team_key(team))
            if team_progress_level == FINALIST:
                if AwardType.WINNER in team_event.awards:
                    team_progress_level = WINNER
            team_event.elimination_progress = team_progress_level
            team_event.put()


def proccess_event_data(raw_data, match_data, event_id):
    root_event = RootEvent.get_or_insert(root_event_key(event_id).id())
    team_list = []
    for i, data in enumerate(raw_data):
        if i != 0:
            #Gets or inserts based on the key of the team_event
            team_event = TeamEvent.get_or_insert(team_event_key(team_key(data[1]), event_id).id(), parent=team_key(data[1]))
            #Stores all of the data for the team_event in the appropriate locations
            team_event.rank = int(Decimal(data[0]))
#             team_event.qualification_score = int(Decimal(data[2]))
#             team_event.assist_points = int(Decimal(data[3]))
#             team_event.autonomous_points = int(Decimal(data[4]))
#             team_event.truss_and_catch_points = int(Decimal(data[5]))
#             team_event.teleop_points = int(Decimal(data[6]))
            team_event.win = int(Decimal(data[7].split('-')[0]))
            team_event.loss = int(Decimal(data[7].split('-')[1]))
            team_event.tie = int(Decimal(data[7].split('-')[2]))
#             team_event.disqualified = int(Decimal(data[8]))
            team_event.played = int(Decimal(data[9]))
            team_event.put()
            #Builds a list of teams at this event
            team_list.append(int(data[1]))
    #Store the root event team list data
    root_event.teams = team_list
    root_event_raw_data = get_data_from_web(globals.event_url, event_id)
    root_event.name = root_event_raw_data['name']
    root_event.put()

    alliance_data = root_event_raw_data['alliances']
    proccess_elimination_progress(match_data, alliance_data)


def proccess_event_awards(raw_data, team_number, event_id):
    event_award_types = []
    event_award_names = []
    if len(raw_data) != 0:
        for data in raw_data: #Iterates through this team's awards at this event
            event_award_types.append(data['award_type'])
            event_award_names.append(data['name'])
    team_event = TeamEvent.get_or_insert(team_event_key(team_key(team_number), event_id).id(), parent=team_key(team_number))
    team_event.awards = event_award_types
    team_event.award_names = event_award_names
    team_event.put()


def proccess_team_data(raw_data, team_number):
    root_team = RootTeam.get_or_insert(root_team_key(team_number).id())
    event_list = []
    for data in raw_data:
        event_list.append(data['key'])
    root_team.events = event_list
    root_team_data = get_data_from_web(globals.team_url, team_number)
    root_team.name = root_team_data['nickname']
    root_team.address = root_team_data['location']
    root_team.put()

def classifyin_weeks_and_takin_names():
    raw_data = get_data_from_web(globals.events_url, globals.year)
    for event in raw_data:
        root_event = RootEvent.get_or_insert(root_event_key(event['key']).id())
        week = convert_date_time_to_week(date(int(event['start_date'].split('-')[0]),int(event['start_date'].split('-')[1]),int(event['start_date'].split('-')[2])))
        root_event.week = week
        root_event.name = event['short_name']
        root_event.put()

def convert_date_time_to_week(date):
    """Date is a timedate object"""
    start_date = date
    time_delta = start_date - globals.first_event_wednesday
    week = int(math.floor((time_delta.days / 7) + 1))
    if week < 0 or week > 7:
        week = 0
    return week

def setup_default_league():
    league = League.get_or_insert('0')
    league.draft_current_position = 0
    league.name = "Not in a league"
    league.put()

class UpdateDB(webapp2.RequestHandler):
    def get(self):
        setup_default_league()
        raw_data = get_data_from_web(globals.rankings_url, '2014txsa')
        match_data = get_data_from_web(globals.event_matches_url, '2014txsa')
        proccess_event_data(raw_data, match_data, '2014txsa')
        alamo_teams = root_event_key('2014txsa').get().teams
        for team in alamo_teams:
            raw_data = get_data_from_web(globals.team_events_url, str(team))
            proccess_team_data(raw_data, str(team))
            raw_data = get_data_from_web(globals.team_event_awards_url, str(team), '2014txsa')
            proccess_event_awards(raw_data, str(team), '2014txsa')

        classifyin_weeks_and_takin_names()
        geocode_within_limit()
        update_total_points()
        self.redirect(self.request.referer)

    def handle_exception(self, exception, debug_mode):
        if debug_mode:
            super(type(self), self).handle_exception(exception, debug_mode)
        else:
            template = JINJA_ENVIRONMENT.get_template('templates/500.html')
            self.response.write(template.render())


class ClearLeagueData(webapp2.RequestHandler):
    def get(self):
        accountQuery = Account.query()
        accounts = accountQuery.fetch()
        for account in accounts:
            account.key.delete()
        choiceQuery = Choice.query()
        choices = choiceQuery.fetch()
        for choice in choices:
            choice.key.delete()
        draftPickQuery = DraftPick.query()
        draftPicks = draftPickQuery.fetch()
        for draftPick in draftPicks:
            draftPick.key.delete()
        lineupQuery = Lineup.query()
        lineups = lineupQuery.fetch()
        for lineup in lineups:
            lineup.key.delete()
        leagueQuery = League.query()
        leagues = leagueQuery.fetch()
        for league in leagues:
            league.key.delete()
        self.redirect(self.request.referer)

    def handle_exception(self, exception, debug_mode):
        if debug_mode:
            super(type(self), self).handle_exception(exception, debug_mode)
        else:
            template = JINJA_ENVIRONMENT.get_template('templates/500.html')
            self.response.write(template.render())


class RunWeekBegin(webapp2.RequestHandler):
    def get(self, week):
        run_week_begin(week)
        self.redirect(self.request.referer)

    def handle_exception(self, exception, debug_mode):
        if debug_mode:
            super(type(self), self).handle_exception(exception, debug_mode)
        else:
            template = JINJA_ENVIRONMENT.get_template('templates/500.html')
            self.response.write(template.render())

class RunProcessing(webapp2.RequestHandler):
    def get(self, week):
        all_leagues = League.query().fetch()
        for league in all_leagues:
            if league.draft_current_position == -1:
                finish_week(league.key.id(), int(week))
        self.redirect(self.request.referer)

    def handle_exception(self, exception, debug_mode):
        if debug_mode:
            super(type(self), self).handle_exception(exception, debug_mode)
        else:
            template = JINJA_ENVIRONMENT.get_template('templates/500.html')
            self.response.write(template.render())


class ShowAdmin(webapp2.RequestHandler):
    def get(self):
        #Send html data to browser
        template_values = {
                    'week': globals.get_current_editable_week(),
                    'week_earlier': globals.get_current_editable_week()-1,
                    }
        template = JINJA_ENVIRONMENT.get_template('templates/adminPage.html')
        self.response.write(template.render(template_values))

    def handle_exception(self, exception, debug_mode):
        if debug_mode:
            super(type(self), self).handle_exception(exception, debug_mode)
        else:
            template = JINJA_ENVIRONMENT.get_template('templates/500.html')
            self.response.write(template.render())


class PageNotFoundHandler(webapp2.RequestHandler):
    def get(self):
        self.error(404)
        template = JINJA_ENVIRONMENT.get_template('templates/404.html')
        self.response.write(template.render())


application = webapp2.WSGIApplication([
                                       ('/updateTeams/clear', ClearLeagueData),
                                       ('/updateTeams/fullData', UpdateDB),
                                       ('/updateTeams/lock/(.*)', RunWeekBegin),  # Week number
                                       ('/updateTeams/process/(.*)', RunProcessing),  # Week number
                                       ('/updateTeams/', ShowAdmin),
                                       ('/updateTeams/.*', PageNotFoundHandler)
                                       ], debug=True)

def main():
    logging.getLogger().setLevel(logging.DEBUG)
    run_wsgi_app(application)

if __name__ == "__main__":
    main()