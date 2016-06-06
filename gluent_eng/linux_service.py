#! /bin/env python
""" Linux 'service' abstraction

    Simplified version of "service" command that operates based on a
    YAML file with the following contents:

    <service name>:
        user: <service user>
        start: <start command>
        stop: <stop command>
        status: <status command>
        pid: <find pid command> (optional)
"""

import logging
import re
import time
import yaml

from termcolor import colored

from .linux_cmd import LinuxCmd
from .process_logs import ProcessLogs


###############################################################################
# EXCEPTIONS
###############################################################################
class LinuxServiceException(Exception): pass


###############################################################################
# CONSTANTS
###############################################################################

# Extract port # and pid from 'netstat -lpn' output
RE_NETSTAT_PORT = re.compile('^(tcp|udp)\s+\d+\s+\d+\s+(\S+:\d+).*\s+(\d+)\/\S+$')

# Default 'process execution' user
DEFAULT_USER='root'


###############################################################################
# LOGGING
###############################################################################
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler()) # Disabling logging by default


class LinuxService(object):
    """ Linux "service" interface
    """
    SUPPORTED_COMMANDS = ['start', 'stop', 'status']

    def __init__(self, config_file, user=DEFAULT_USER, host=None, log_filter=None, extended=False, wait=None):
        """ CONSTRUCTOR
            
            Parameters:
                1: (YAML) config file with a list of services defined as:
                    <service name>:
                        user: <service user>
                        start: <start command>
                        stop: <stop command>
                        status: <status command>
                        pid: <find pid command> (optional)
                2,3: user, host: User and host to run commands as
                4: extended: True|False - whether to display 'extended' service info,
                       such as ports, log files etc
                5: wait: Default 'wait' in seconds after each command is run (None: 'do not wait')
        """
        self._services = self._read_config(config_file)

        # Linux command 'runner'
        self._linux = LinuxCmd(user=user, host=host)
        self._user = user
        self._host = host
        self._wait = float(wait) if wait is not None else None

        if extended:
            self._extended = True
            self._ports = self._get_all_ports()
            self._plogs = ProcessLogs(user=user, host=host, log_filter=log_filter)
        else:
            self._extended = False
            self._ports = {}
            self._plogs = None

        logger.debug("LinuxService() object successfully initialized")


    def _read_config(self, config_file):
        """ Read (YAML) config file and return contents """
        data = None

        logger.info("Reading from (YAML) config file: %s" % config_file)

        with open(config_file) as f:
            data = yaml.safe_load(f)

        logger.debug("Config data: %s" % data)

        return data


    def _execute(self, cmd, user):
        """ Execute linux command, validate and return result
        """
        if self._linux.execute(cmd, user=user):
            success = self._linux.success and not self._linux.stderr
            return success, self._linux.stdout
        else:
            logger.warn("Error: %s executing linux command: %s" % (self._linux.stderr, cmd))
            # All commands may 'fail' for a good reason
            return None, None


    def _wait_for_completion(self, service):
        """ Wait N seconds after executing 'state change' service command
            (poor's man way to to let state 'properly propagate')
        """
        wait_in_seconds = self._wait

        if service not in self._services:
            raise LinuxServiceException("Cannot find service: %s" % service)

        if 'wait' in self._services[service]:
            wait_in_seconds = float(self._services[service]['wait'])
            logger.debug("Found wait: %.2f for service: %s" % (wait_in_seconds, service))
        else:
            logger.debug("Specific wait NOT found for service: %s. Assuming: 'default': %s" % \
                (service, wait_in_seconds))
        
        if wait_in_seconds:
            logger.info("Waiting %.2f seconds to let state propagate for service: %s" % (wait_in_seconds, service))
            time.sleep(wait_in_seconds)
        else:
            logger.debug("Skipping 'state propagation' wait for service: %s" % service)


    def _get_user(self, service):
        """ Return service user from 'user' entry in config file

            If user entry does not exist, return None (i.e. "current user")
        """
        user = self._user

        if service not in self._services:
            raise LinuxServiceException("Cannot find service: %s" % service)

        if 'user' in self._services[service]:
            user = self._services[service]['user']
            logger.debug("Found user: %s for service: %s" % (user, service))
        else:
            logger.debug("Specific user NOT found for service: %s. Assuming: 'current user'" % \
                service)
        
        return user


    def _find_pid(self, service):
        """ Find PID for the supplied service
        """
        logger.debug("Finding PID for service: %s" % service)

        # We need to know how to find PID of the service:
        #    that is, have the actual command in 'pid' entry of the config file
        if 'pid' not in self._services[service]:
            logger.warn("Do not know how to find PID for service: %s" % service)
            return None

        # Ok, let's run the command to find it
        user = self._get_user(service)
        success, pid = self._execute(self._services[service]['pid'], user)

        # And check if we actually found anything
        if not success or not pid:
            logger.debug("Inable to find PID for service: %s" % service)
            # Returning None rather than throwing an exception to facilitate
            # normal processing when we cannot find 'working pid' (i.e. when the service is down)
            return None

        pid = int(pid)
        logger.debug("Found PID: %d for service: %s" % (pid, service))

        return pid

    
    def _get_all_ports(self):
        """ Query OS for open (tcp) ports
        """
        open_ports = {}

        cmd = "netstat -lpn | grep -P 'tcp|udp'"
        success, result = self._execute(cmd, self._user)

        if success and result:
            for line in result.split('\n'):
                line = line.strip()
                match = RE_NETSTAT_PORT.search(line)
                if match:
                    proto, port, pid = match.groups()
                    pid = int(pid)
                    if pid not in open_ports:
                        open_ports[pid] = []
                    open_ports[pid].append("%s: %s" % (proto, port))
        else:
            logger.warn("Found no open TCP ports")

        # Make list of ports/per-process unique and sorted
        for pid in open_ports:
            open_ports[pid] = sorted(list(set(open_ports[pid])))
                
        logger.debug("Extracted TCP ports: %s" % open_ports)
        return open_ports


    def _find_ports(self, pid):
        """ Get ports for pid
        """
        ports = self._ports[pid] if pid in self._ports else None
        logger.debug("Identified ports: %s for pid: %d" % (ports, pid))
        return ports


    def _find_logs(self, pid):
        """ Get logs for pid
        """
        if self._plogs:
            logs = sorted(self._plogs.by_pid(pid).keys())
            logger.debug("Identified logs: %s for pid: %d" % (logs, pid))
            return logs
        else:
            raise LinuxServiceException("Attempt to extract logs with un-initialized ProcessLogs() object")


    def _exec_service_command(self, service, cmd):
        """ Execute command for a specified service

            Returns: success: True|False, "command output"
        """
        cmd = cmd.lower()

        logger.debug("Executing command: %s for service: %s" % (cmd, service))

        if service not in self._services:
            raise LinuxServiceException("Unknown service: %s" % service)

        if cmd not in self.SUPPORTED_COMMANDS:
            raise LinuxServiceException("Unsupported command: %s" % cmd)

        run_cmd = self._services[service][cmd]
	logger.debug("Using '%s' command: '%s' for service: %s" % \
            (cmd, run_cmd, service))

        # Grab 'user' if defined
        # Otherwise, use 'current' user
        user = self._get_user(service)

        success, output = self._execute(run_cmd, user)

        return success, output


    def _print_status(self, service, success):
        """ Print status message for a specified service """
        status = 'UNDEF'

        if success is None:
            status = colored("NOOP", "yellow", attrs=['bold'])
        elif success:
            status = colored("OK", "green", attrs=['bold'])
        else:
            status = colored("FAIL", "red", attrs=['bold'])
        
        status_msg = "%-50s[ %s ]" % (service, status)

        # Extended output requested ?
        if self._extended:
            pid = self._find_pid(service)

            if pid:
                status_msg += "\n\tPID: %d" % pid

                ports = self._find_ports(pid)
                if ports:
                    status_msg += "\n\tPORTS:\n\t\t%s" % "\n\t\t".join(ports)

                logs = self._find_logs(pid)
                if logs:
                    status_msg += "\n\tLOGS:\n\t\t%s" % "\n\t\t".join(logs)

                # Last \n to separate different services
                status_msg += "\n"

        print(status_msg)


    #####################################################################
    # PUBLIC ROUTINES
    #####################################################################

    def start(self, service):
        """ Run service 'start' command
        """
        logger.info("Starting service: %s" % service)

        # First, check the status. Do nothing if service is already running
        success, output = self._exec_service_command(service, 'status')

        if success and output:
            self._print_status(service, None) # Print NOOP
        else:
            success, output = self._exec_service_command(service, 'start')
            self._print_status(service, success)

        return success, output


    def stop(self, service):
        """ Run service 'stop' command
        """
        logger.info("Stopping service: %s" % service)

        # First, check the status. Do nothing if service is not running
        success, output = self._exec_service_command(service, 'status')

        if not success or not output:
            self._print_status(service, None) # Print NOOP
        else:
            success, output = self._exec_service_command(service, 'stop')
            self._print_status(service, success)

        return success, output


    def status(self, service):
        """ Run service 'status' command
        """
        logger.info("Checking status for service: %s" % service)

        success, output = self._exec_service_command(service, 'status')
        # Special case fo 'status' - empty output == "not running"
        if not output:
            success = False
        self._print_status(service, success)

        return success, output


    def run(self, service, cmd):
        """ Parse 'service' regex and schedule 'commands' on, potentially,
            multiple services defined in the configuration file

            I.e. service='hdfs' may expand to: ['hdfs-namenode', 'hdfs-datanode']
                 service='yarn' may expand to: ['yarn-resourcemanager', 'yarn-nodemanager']
                 etc

            Special case: service='all', self explanatory
        """
        if cmd not in self.SUPPORTED_COMMANDS:
            raise LinuxServiceException("Unsupported command: %s" % cmd)

        # Special case for 'all'
        if 'all' == service:
            service='.*'

        reX = re.compile(service)

        # Expand service list
        target_services = [_ for _ in self._services if reX.search(_)]

        # 'start', 'status': increasing 'sequence' order
        # 'stop': decreasing order
        use_reverse = False
        if cmd in ('stop'):
            use_reverse = True

        service_list = sorted(target_services, key=lambda x: self._services[x]['sequence'], \
            reverse=use_reverse)

        logger.info('Service: %s has been expanded to: %s for command: %s' % \
            (service, service_list, cmd))

        # Execute the command(s)
        for service in service_list:
            getattr(self, cmd)(service)
            if cmd in ('start', 'stop'):
                self._wait_for_completion(service)
