#!/usr/bin/python
"""*****************************************************************************************************************
    Pi Remind HD Notify
    Created April 4, 2020.
    By John M. Wargo (https://www.johnwargo.com)

    This application connects to a Google Calendar and determines whether there are any appointments in the next
    few minutes and flashes some LEDs if there are. The project uses a Raspberry Pi 2 device with a Pimoroni
    Unicorn HAT HD (a 16x16 matrix of bright, multi-colored LEDs) to display an obnoxious reminder every minute,
    changing color at 10 minutes (WHITE), 5 minutes (YELLOW) and 2 minutes (multi-color swirl).

    Coupled with the Remote Notify project, the server code sends appointment status to the remote notify device
    to make others aware of the user's status (busy, tentative, free).

    Google Calendar example code: https://developers.google.com/google-apps/calendar/quickstart/python
********************************************************************************************************************"""
# TODO: Clean up imports
from __future__ import print_function

# This project's imports (local modules)
from google_calendar import GoogleCalendar
from particle import *
from status import Status
import unicorn_hat as unicorn
#  Other imports
import datetime
import json
import logging
import sys
import time

# Pulled this 05/01/2020 because its never used
# from oauth2client import client, file, tools
# try:
#     import argparse
#     flags = argparse.ArgumentParser(parents=[tools.argparser]).parse_args()
# except ImportError:
#     flags = None

HASH = '#'
HASHES = '#############################################'
PROJECT_URL = 'https://github.com/johnwargo/pi-remind-hd-notify'
CONFIG_ERROR_STR = 'Please validate the contents of the config.json file before continuing'

# Event search scope (searches this many minutes in the future for events). Increase this value to get reminders
# earlier. The app displays WHITE lights from this limit up to FIRST_THRESHOLD
# TODO: Make this a config setting
SEARCH_LIMIT = 10  # minutes
# Reminder thresholds
FIRST_THRESHOLD = 5  # minutes, WHITE lights before this
# RED for anything less than (and including) the second threshold
SECOND_THRESHOLD = 2  # minutes, YELLOW lights before this

# the config object properties, used when validating the config
CONFIG_PROPERTIES = ["access_token", "debug_mode", "device_id", "ignore_tentative_appointments",
                     "reboot_counter_limit", "use_reboot_counter", "use_remote_notify"]

# initialize the classes we'll use as globals
cal = None  # Google Calendar
particle = None  # Particle Cloud

debug_mode = False
# whether or not you have a remote notify device connected. Use the config file to override
use_remote_notify = False


def validate_config(config_object):
    # Returns a lit of missing attributes for the object
    # These logging statements are info because debug won't be set until after
    # the app validates the config file
    logging.debug('Validating configuration file')
    res = []
    for i, val in enumerate(CONFIG_PROPERTIES):
        try:
            prop = config_object[val]
            logging.info("Configuration property '{}' exists".format(val))
        except KeyError:
            logging.info("Configuration property '{}' missing".format(val))
            res.append(val)
    return len(res) < 1, ','.join(res)


def processing_loop():
    global cal, particle

    # initialize the previous remote notify status
    previous_status = -1

    # initialize the lastMinute variable to the current time to start
    last_minute = datetime.datetime.now().minute
    # on startup, just use the previous minute as lastMinute, that way the app
    # will check for appointments immediately on startup.
    if last_minute == 0:
        last_minute = 59
    else:
        last_minute -= 1
    # infinite loop to continuously check Google Calendar for future entries
    while 1:
        # get the current minute
        current_minute = datetime.datetime.now().minute
        # is it the same minute as the last time we checked?
        if current_minute != last_minute:
            # reset last_minute to the current_minute, of course
            last_minute = current_minute
            # we've moved a minute, so we have work to do
            # get the next calendar event (within the specified time limit [in minutes])
            next_event = cal.get_next_event()
            # next_event = cal.get_status()
            # do we get an event?
            if next_event is not None:
                num_minutes = next_event['num_minutes']
                if num_minutes != 1:
                    logging.info('Starts in {} minutes\n'.format(num_minutes))
                else:
                    logging.info('Starts in 1 minute\n')
                # is the appointment between 10 and 5 minutes from now?
                if num_minutes >= FIRST_THRESHOLD:
                    # Flash the lights in WHITE
                    unicorn.flash_all(1, 0.25, unicorn.WHITE)
                    # display the event summary
                    unicorn.display_text(next_event['summary'], unicorn.WHITE)
                    # set the activity light to WHITE as an indicator
                    unicorn.set_activity_light(unicorn.WHITE, False)
                # is the appointment less than 5 minutes but more than 2 minutes from now?
                elif num_minutes > SECOND_THRESHOLD:
                    # Flash the lights YELLOW
                    unicorn.flash_all(2, 0.25, unicorn.YELLOW)
                    # display the event summary
                    unicorn.display_text(next_event['summary'], unicorn.YELLOW)
                    # set the activity light to YELLOw as an indicator
                    unicorn.set_activity_light(unicorn.YELLOW, False)
                else:
                    # hmmm, less than 2 minutes, almost time to start!
                    # swirl the lights. Longer every second closer to start time
                    unicorn.do_swirl(int((4 - num_minutes) * 50))
                    # display the event summary
                    unicorn.display_text(next_event['summary'], unicorn.ORANGE)
                    # set the activity light to SUCCESS_COLOR (green by default)
                    unicorn.set_activity_light(unicorn.ORANGE, False)

                # should we update a remote notify device?
                if use_remote_notify:
                    # get status from the results
                    # TODO: Change this
                    current_status = Status.BUSY
                    # Only change the status if it's different than the current status
                    if current_status != previous_status:
                        # update the remote device status
                        previous_status = current_status
                        particle.set_status(current_status)

        # wait a second then check again
        # You can always increase the sleep value below to check less often
        time.sleep(1)


def main():
    global debug_mode, cal, particle, use_remote_notify

    # Setup the logger
    # TODO: omit milliseconds from time value
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # tell the user what we're doing...
    print('\n')
    print(HASHES)
    print(HASH, 'Pi Remind HD Notify                      ', HASH)
    print(HASH, 'By John M. Wargo (https://johnwargo.com) ', HASH)
    print(HASHES)
    print('Project: ' + PROJECT_URL + '\n')

    logging.info('Remind: Opening project configuration file (config.json)')
    # Read the config file contents
    # https://martin-thoma.com/configuration-files-in-python/
    with open("config.json") as json_data_file:
        config = json.load(json_data_file)
    #  did the config read correctly?
    if config:
        valid_config, config_errors = validate_config(config)
        if valid_config:
            logging.info('Remind: Configuration file is valid')
            use_remote_notify = config['use_remote_notify']
            use_reboot_counter = config['use_reboot_counter']
            reboot_counter_limit = config['reboot_counter_limit']
        else:
            logging.error('Remind: The configuration file is missing one or more properties')
            logging.error('Missing values: ' + config_errors)
            logging.error(CONFIG_ERROR_STR)
            sys.exit(0)
    else:
        logging.error('Remind: Unable to read the configuration file')
        logging.error(CONFIG_ERROR_STR)
        sys.exit(0)

    debug_mode = config['debug_mode']
    if debug_mode:
        logging.info('Remind: Enabling debug mode')
        logger.setLevel(logging.DEBUG)

    if use_remote_notify:
        logging.info('Remind: Remote Notify Enabled')
        access_token = config['access_token']
        device_id = config['device_id']
        # Check to see if the string values we need are populated
        if len(access_token) < 1 or len(device_id) < 1:
            logging.error('One or more values are missing from the project configuration file')
            logging.error(CONFIG_ERROR_STR)
            sys.exit(0)
        logging.debug('Remind: Creating Particle object')
        particle = ParticleCloud(access_token, device_id)

        logging.info('Remind: Resetting Remote Notify status')
        particle.set_status(Status.FREE)
        time.sleep(1)
        particle.set_status(Status.OFF)

    if use_reboot_counter:
        logging.info('Remind: Reboot enabled ({} retries)'.format(reboot_counter_limit))

    logging.info('Remind: Initializing Google Calendar interface')
    try:
        cal = GoogleCalendar(
            # TODO: Make this a configurable setting
            SEARCH_LIMIT,
            config['ignore_tentative_appointments'],
            use_reboot_counter,
            reboot_counter_limit
        )
    except Exception as e:
        logging.error('Remind: Unable to initialize Google Calendar API')
        logging.error('Exception type: {}'.format(type(e)))
        logging.error('Error: {}'.format(sys.exc_info()[0]))
        unicorn.set_all(unicorn.FAILURE_COLOR)
        time.sleep(5)
        unicorn.off()
        sys.exit(0)

    logging.info('Remind: Application initialized\n')

    # flash some random LEDs just for fun...
    unicorn.flash_random(5, 0.5)
    # blink all the LEDs GREEN to let the user know the hardware is working
    unicorn.flash_all(3, 0.10, unicorn.GREEN)
    # get to work
    processing_loop()


if __name__ == '__main__':
    try:
        # Initialize the Unicorn HAT
        unicorn.init()
        # do our stuff
        main()
    except KeyboardInterrupt:
        # turn off all of the LEDs
        unicorn.off()
        # tell the user we're exiting
        logging.info('\nExiting application\n')
        # exit the application
        sys.exit(0)
