#! /usr/bin/env python
""" PtailRunner: High level 'process tail' interface

    Provides basic: show() and tail() primitives.

    Handles 'process tail' logic for dynamic list of logs
    (i.e. 'relevant logs' might change as processes open/close them)
"""

import logging

from datetime import datetime, timedelta

from .file_tailer import FileTailer
from .log_setup import DEFAULT_LOG_ENTRY
from .process_logs import ProcessLogs, METHOD_PID, METHOD_NAME_REGEX, ALLOWED_METHODS


###############################################################################
# EXCEPTIONS
###############################################################################

###############################################################################
# CONSTANTS
###############################################################################

###############################################################################
# LOGGING
###############################################################################
logger = logging.getLogger(__name__)
#logger.addHandler(logging.NullHandler()) # Disabling logging by default


class PtailRunner(object):
    """ High level 'process tail' interface """

    def __init__(self, refresh_interval, method, search_key, log_filter, from_top, full_color, simple_grep, user, config_file):
        assert method in ALLOWED_METHODS

        self._refresh_interval = refresh_interval  # (look for new logs) Refresh interval, in seconds
        self._last_refresh = None                  # Last refresh time

        self._method = method                      # (look for new logs) method, for now: pid or name (see: ALLOWED_METHODS)
        self._search_key = search_key              # Method appropriate 'search key', i.e. 'list of pids' or 'name regex'
        self._log_filter = log_filter              # Log name filter, i.e. '.log' or '.txt|.xml'
        self._from_top = from_top                  # Boolean: whether to scan from the beginning of log
        self._full_color = full_color              # Boolean: Colorize "the entire line" in 'log color' if True
        self._simple_grep = simple_grep            # Use 'simple grep' model, when filtering log lines to be output

        # ProcessLogs object to query UNIX processes for logs
        self._plogs = ProcessLogs(user=user, setup_file=config_file)

        # Log handles
        self._logs_current = {}
        self._logs_prev = {}

        # 'Bad logs' cache - mark files that cannot be opened so that not to process them again
        self._bad_logs = {}

        logger.debug("PtailRunner() successfully initialized")


    ###############################################################################
    # PRIVATE METHODS
    ###############################################################################

    def _get_new_logs(self):
        """ Re-query 'processes' for updated list of logs
        """
        get_call = self._plogs.by_pid if METHOD_PID == self._method else self._plogs.by_name

        new_logs = get_call(self._search_key, self._log_filter)
        return new_logs


    def _adjust_logs(self, new_logs):
        """ Compare previous and current list of logs
            Open 'added' logs, Close 'deleted' logs
        """
        adjusted = False

        current_logs = set(new_logs.keys())
        logger.debug("Current logs: %s" % current_logs)
        prev_logs = set([self._logs_prev[_].name for _ in self._logs_prev])

        added_logs = list(current_logs - prev_logs)
        logger.info("Identified: %d new logs: %s" % (len(added_logs), added_logs))
        deleted_logs = list(prev_logs - current_logs)
        logger.info("Identified: %d closed logs: %s" % (len(deleted_logs), deleted_logs))

        # Process 'added' logs
        for log in added_logs:
            if log in self._bad_logs:
                logger.debug("Log: %s is 'bad' (permissions ?). Not processing it" % log)
                continue

            color, format, label = new_logs[log]['color'], new_logs[log]['format'], new_logs[log]['label']
            if self._simple_grep:
                logger.debug("Simple 'grep' requested. Forcing trivial log line format")
                format = DEFAULT_LOG_ENTRY

            logger.debug("Adding new log: %s" % log)
            new_log = FileTailer(log, color, self._full_color, format, label)
            if new_log.open(self._from_top):
                self._logs_current[log] = new_log
                adjusted = True
            else:
                logger.warn("Unable to open log: %s. Marking as 'bad'" % log)
                self._bad_logs[log] = True

        # Process 'deleted' logs
        for log in deleted_logs:
            logger.debug("Removing log: %s as it appears to have been closed" % log)
            self._logs_current[log].close()
            del self._logs_current[log]
            adjusted = True

        return adjusted


    def _refresh_logs_if_necessary(self, open_logs):
        """ Refresh logs if 1st time or 'refresh interval' expired
        """
        now = datetime.now()
        interval_expired = self._refresh_interval and \
            (not self._last_refresh or \
            self._last_refresh + timedelta(seconds=self._refresh_interval) < now)

        if not self._logs_current or interval_expired:
            # self._logs_prev = {k: v for k, v in self._logs_current.items()} # Need a true {} copy 2.7+
            self._logs_prev = dict((k, v) for k, v in self._logs_current.items()) # Need a true {} copy
            new_logs = self._get_new_logs()  # Get new logs from 'processes'
            if open_logs:
                if self._adjust_logs(new_logs):  # Open/close files and set new self._logs_current
                    print "" # Empty line after all logs have been announced
            self._last_refresh = now


    ###############################################################################
    # PUBLIC METHODS
    ###############################################################################

    def tail(self, filters, highlight):
        """ Tail 'current' logs
        """
        self._refresh_logs_if_necessary(open_logs=True)

        if 0 == len(self._logs_current):
            # print "No logs qualified"
            pass
        else:
            for log in self._logs_current:
                self._logs_current[log].tail(filters, highlight)


    def show(self):
        """ Print process information + logs
        """
        self._refresh_logs_if_necessary(open_logs=False)
        process_info = self._plogs.process_info

        for proc in sorted(process_info, key=lambda c: c['cmd']):
            # Only show info where logs exist
            if proc['logs']:
                print "\n%s:" % proc['cmd']
                print "\tPID: %d" % proc['pid']
                print "\tCOMMAND LINE: %s" % proc['full_cmd']
                print "\tLOGS:"
                for log in sorted(proc['logs']):
                    print "\t\t%s" % log

