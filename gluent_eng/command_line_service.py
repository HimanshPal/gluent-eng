#! /bin/env python
""" Command line for 'service.py'
"""

import argparse
import logging
import sys

from .linux_service import LinuxService, LinuxServiceException, DEFAULT_ROOT_USER
from .process_logs import RE_DEFAULT_LOG_NAME_FILTER


###############################################################################
# EXCEPTIONS
###############################################################################

PROG_BANNER = "SERVICE: Simplified Linux service interface"

# Default logging level
DEFAULT_LOGGING = "CRITICAL"


###############################################################################
# LOGGING
###############################################################################
logger = logging.getLogger("service")
#logger.addHandler(logging.NullHandler()) # Disabling logging by default


# -----------------------------------------------------------------------
# Standalone Routines
# -----------------------------------------------------------------------

def set_logging(log_level):
    """ Set "global" logging parameters
    """

    logging.basicConfig(
        level=logging.getLevelName(log_level),
        format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def print_title():
    """ Print utility title """

    print "%s\n" % PROG_BANNER


def parse_args():
    """
      Parse arguments and return "options" object
    """

    parser = argparse.ArgumentParser(description=PROG_BANNER)

    parser.add_argument('-c', '--config-file', required=True, help="(service) Configuration file")

    parser.add_argument('-u', '--root-user', required=False, default=DEFAULT_ROOT_USER, \
        help="User to run 'privileged' linux commands as. Default: %s" % DEFAULT_ROOT_USER)
    parser.add_argument('-H', '--host', required=False, help="Host to run linux commands on. Default: localhost")

    parser.add_argument('-e', '--extended', required=False, action='store_true', help="Extended output")
    parser.add_argument('-L', '--log-filter', required=False, \
        help="Log name filter (regex) for extended output. Default: %s" % RE_DEFAULT_LOG_NAME_FILTER.pattern)

    parser.add_argument('-w', '--wait', required=False, type=float, help="Wait (in seconds) after running start/stop command")

    parser.add_argument('-l', '--log-level', required=False, default=DEFAULT_LOGGING, \
        help="Logging level. Default: %s" % DEFAULT_LOGGING)

    parser.add_argument('service', help="Service name")
    parser.add_argument('command', help="Command to execute", choices=['start', 'stop', 'status'])

    args = parser.parse_args()

    # Args post-processing
    args.log_level = args.log_level.upper()

    #if args.extended and args.command not in ('status'):
    #    raise LinuxServiceException("Extended mode only makes sense with 'status' command")

    return args


def main():
    """
      MAIN ROUTINE
    """
    args = parse_args()

    print_title()

    # Set up logging
    set_logging(args.log_level)

    # Initialize service object
    srv = LinuxService(
        config_file = args.config_file,
        root_user = args.root_user,
        host = args.host,
        log_filter = args.log_filter,
        extended = args.extended,
        wait = args.wait
    )

    # Run service command
    srv.run(args.service, args.command)

    sys.exit(0)
