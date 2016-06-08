#! /usr/bin/env python
"""  Main script 'routines' for PTAIL script
"""

import argparse
import logging
import re
import sys
import time

from process_logs import METHOD_PID, METHOD_NAME_REGEX
from .ptail_runner import PtailRunner


###############################################################################
# EXCEPTIONS
###############################################################################


###############################################################################
# CONSTANTS
###############################################################################

PROG_BANNER = "PTAIL: Discover and tail logs for running processes"

# Default logging level
DEFAULT_LOGGING = "CRITICAL"

# How long to wait for new lines in a tailed file
DEFAULT_NEWLINES_WAIT = 0.5
# How frequently to 'refresh' list of logs
DEFAULT_NEWLOGS_WAIT = 0.5

# Default config file
DEFAULT_CONFIG = "ptail.yaml"

# Default user to execute linux commands
DEFAULT_USER = 'root'


###############################################################################
# LOGGING
###############################################################################
logger = logging.getLogger("ptail")
#logger.addHandler(logging.NullHandler()) # Disabling logging by default


# -----------------------------------------------------------------------
# Standalone Routines
# -----------------------------------------------------------------------

def set_logging(log_level):
    logging.basicConfig(
        level=logging.getLevelName(log_level),
        format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def print_title():
    """ Print utility title """
    print "%s\n" % PROG_BANNER


def make_where_dict(where):
    """
        Take FILTER string in the format: level=DEBUG,text=app_123
        and transform it into dictionary: {'level': 'DEBUG', 'text': 'app_123'}
        that can be passed as KWARGS to the function
    """
    where_d = {}
    for l in where.strip().split(','):
        k, v = l.split('=')
        where_d[k] = v

    return where_d


def parse_args():
    """ Parse arguments and return "options" object
    """
    parser = argparse.ArgumentParser(description=PROG_BANNER)

    parser.add_argument('-c', '--config-file', required=False, default=DEFAULT_CONFIG, \
        help="Configuration file. Default: %s" % DEFAULT_CONFIG)

    operation = parser.add_mutually_exclusive_group(required=False)
    operation.add_argument('-s', '--show-logs', action='store_true', help="Show logs")
    operation.add_argument('-f', '--continuous', action='store_true', help="Tail -f mode (default)")

    parser.add_argument('-b', '--from-top', required=False, action='store_true', \
        help="Scan log files from the beginning")

    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('-p', '--pid', nargs='+', type=int, help="Select processes with these pids")
    source.add_argument('-N', '--name', help="Select processes with this (regex) name pattern")

    parser.add_argument('-L', '--log-filter', required=False, default=None, help="Log name filter")

    parser.add_argument('-u', '--user', required=False, default=DEFAULT_USER, \
        help="User to run linux commands as. Default: %s" % DEFAULT_USER)

    parser.add_argument('-w', '--wait', required=False, type=float, \
        default=DEFAULT_NEWLINES_WAIT, \
        help="Wait (in seconds) for new file lines. Default: %.2f" % DEFAULT_NEWLINES_WAIT)
    parser.add_argument('-r', '--refresh-interval', required=False, type=float, \
        default=DEFAULT_NEWLOGS_WAIT, \
        help='Refresh list of logs every N seconds. Default: %.2f' % DEFAULT_NEWLOGS_WAIT)

    parser.add_argument('-l', '--log-level', required=False, default=DEFAULT_LOGGING, \
        help="Logging level. Default: %s" % DEFAULT_LOGGING)

    parser.add_argument('-H', '--highlight', required=False, \
        help='Highlight specified entries (supports regular expressions)')
    parser.add_argument('-C', '--full-color', required=False, action='store_true', \
        help='Highlight specified entries')

    filters = parser.add_mutually_exclusive_group(required=False)
    filters.add_argument('-F', '--filters', nargs='+', help="""
        (line) 'Structured' line selection filters, i.e.: --filters level=INFO text=Driver

        If 'line format' is defined (in configuration file), and incoming log line matches 
        log line is broken down into 'columns' with each column becoming individually 'searchable' (see above)
        Line is output is it passes ALL filters
        (if 'line format' is not supplied, default is: 'whole line' is a 'text' column)
        Values are regular expressions

        [EXPERIMENTAL]
    """)
    filters.add_argument('-G', '--grep', help="""
        (line) 'Simple' line selection filter: i.e. --grep log.PerfLogger

        Essentially, 'grep': Line is output if it passes the (regular expression) filter 
        (equivalent to --filters: text=log.PerfLogger)
    """)

    args = parser.parse_args()

    # === Postprocess parameters
    args.log_level = args.log_level.upper()

    if not args.show_logs and not args.continuous:
        args.continuous = True

    # Search by either 'pid' or 'name regex'
    if args.pid:
        args.method = METHOD_PID
        args.search_key = args.pid
    else:
        args.method = METHOD_NAME_REGEX
        args.search_key = args.name

    # Making highlight pattern
    if args.highlight:
        args.highlight = re.compile('('+args.highlight+')', re.M)

    # Compile 'filters'
    if args.filters:
        filters = make_where_dict(",".join(args.filters))
        #args.filters = {_: re.compile(filters[_]) for _ in filters} 2.7+
        args.filters = dict((k, re.compile(filters[k])) for k in filters)
    elif args.grep:
        args.filters = {'text': re.compile(args.grep)}

    return args

def main():
    args = parse_args()
    print_title()
    set_logging(args.log_level)

    runner = PtailRunner(
        refresh_interval = args.refresh_interval, 
        method = args.method,
        search_key = args.search_key,
        log_filter = args.log_filter,
        from_top = args.from_top,
        full_color = args.full_color,
        simple_grep = args.grep,
        user = args.user,
        config_file = args.config_file
    )

    if args.show_logs:
        runner.show()
    else:
        try:
            while True:
                runner.tail(args.filters, args.highlight)
                if not args.continuous:
                    break
                logger.debug("Sleeping: %f seconds" % args.wait)
                time.sleep(args.wait)
        except KeyboardInterrupt:
            print "Detected CTRL+C. Exiting .."

    sys.exit(0)
