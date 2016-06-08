#! /usr/bin/env python
""" ProcessLogs: Discover and present 'logs' from running Linux processes

    Logs = text files with 'relevant' (user controlled) extensions, i.e. .txt or .log
"""

import logging
import os
import os.path
import re
import socket

from .linux_cmd import LinuxCmd
from .log_setup import LogSetup


###############################################################################
# EXCEPTIONS
###############################################################################

class ProcessLogsException(Exception): pass


###############################################################################
# CONSTANTS
###############################################################################

# Regular expressions for parsing various components
RE_JAVA_CLASSES = re.compile('\s+(?![-/])\S+')  # Skip -options and /files

# Default 'log name' filter
RE_DEFAULT_LOG_NAME_FILTER = re.compile('\.(log|trc|out)')

# Remove non-essential elements from log name (when making 'short name')
RE_REMOVE_NON_ESSENTIAL = re.compile('[\d]')
# Non-essential 'last in the name' symbols
RE_LAST_NON_ESSENTIAL = re.compile('[\.\-\_\*]+$')

# Log acquire methods
METHOD_PID = 'pid'
METHOD_NAME_REGEX = 'name'
ALLOWED_METHODS = (METHOD_PID, METHOD_NAME_REGEX)

# Log types
LOG_TYPE_TEXT = 'text'
LOG_TYPE_BINARY = 'binary'
LOG_TYPE_EMPTY = 'empty'

###############################################################################
# LOGGING
###############################################################################
logger = logging.getLogger(__name__)
#logger.addHandler(logging.NullHandler()) # Disabling logging by default


class ProcessLogs(object):
    """ ProcessLogs: Discover log files for specified process(es)

        'List of processes' can be specified by:
            'pids'
            'name regex'

        Log files are filtered out by 'log filter'
    """

    def __init__(self, user=None, host=None, setup_file=None, log_filter=None):
        """ CONSTRUCTOR
 
            user, host:       Run (process/log discovery) linux commands as user, host
            setup_file:       (YAML) configuration file with log metadata (see LogSetup())
        """
        # "returnable" Results
        self._process_info = None
        self._log_info = {}

        """
            LogSetup() object with additional relevant metadata for logs
            i.e.
            {
                'log name pattern': {'color': ..., 'format': ..., 'label': ...},
                'log name pattern': {'color': ..., 'format': ..., 'label': ...},
            }
        """
        self._setup = LogSetup(setup_file)

        # Linux command 'runner'
        self._linux = LinuxCmd(user=user, host=host)

        # Discover various host names (relevant for log parsing)
        self._host_names = self._get_host_names()
    
        # Known logs 'cache'
        self._known_logs = {}

        # 'Default' log filter
        self._log_filter = log_filter

        logger.debug("ProcessLogs() object successfully initialized")


    ###########################################################################
    # PRIVATE ROUTINES
    ###########################################################################

    def _execute(self, cmd):
        """ Execute linux command, validate and return result
        """ 
        if self._linux.execute(cmd):
            return self._linux.stdout
        else:
            raise ProcessLogsException("Error: %s executing linux command: %s" % (self._linux.stderr, cmd))


    def _extract_process_name(self, raw_name):
        """ Extract 'meaningful' process name
        """
        def parse_java_cmd(raw_name):
            """ Extract relevant 'name' from Java process command line """
            cmd = 'java'

            java_classes = RE_JAVA_CLASSES.findall(raw_name)
            # Iterate in reverse as usually relevant classes are at the end
            for cl in reversed(java_classes):
                cl_lower = cl.lower()
                # Skip 'common' keywords
                if any(_ in cl_lower for _ in ('runjar', 'start', '://')):
                    continue

                # Ok, this is our 'final' class, let's find relevant 'keyword'
                for kw in reversed(cl.split('.')):
                    kw_lower = str(kw).lower().strip()
                    # Skip meaningless parts of class
                    if not any(_ == kw_lower for _ in ('main', 'org', 'server', 'templeton', '*')):
                        # Not skipped ? That's our class
                        final_kw = kw.strip()
                        # Final check - there might still be 'meaningless' parts in final_kw
                        if '/' in final_kw:
                            for kwp in reversed(final_kw.split('/')):
                                kwp_lower = kwp.lower()
                                if not any(_ == kwp_lower for _ in ('share', 'java', '*')):
                                    # Not skipped ? - that's the final name
                                    cmd = kwp
                                    break
                        else:
                            cmd = final_kw

                        break

            return cmd

        # _extract_process_name() begins here
        cmd = os.path.basename(raw_name.split(None, 1)[0]).lower()

        # Special processing for Java
        if 'java' == cmd:
            cmd = parse_java_cmd(raw_name)

        return cmd


    def _execute_ps(self, cmd):
        """ Execute ps/pgrep command and process results
        """
        result = self._execute(cmd)
        if not result:
            return []

        proc_info = []
        for proc in result.split('\n'):
            pid, name = proc.split(None, 1)
            proc_info.append({
                'pid': int(pid),
                'cmd': self._extract_process_name(name), # Short 'human readable' process name
                'full_cmd': name,                        # Full command line with options etc
            })

        return proc_info


    def _get_process_info_by_pids(self, pid_list):
        """ Execute 'ps' command for 'pid_list' and return

            [{'pid': .., 'cmd': ..}, ..]
        """
        cmd = "ps -p %s -o pid,cmd --no-headers | grep -v %d" % (",".join([str(_) for _ in pid_list]), os.getpid())
        logger.info("Extracting processes by pid list: %s" % cmd)
        return self._execute_ps(cmd)


    def _get_process_info_by_name(self, re_name):
        """ Execute 'pgrep' command for 're_name' name pattern and return

            [{'pid': .., 'cmd': ..}, ..]
        """
        cmd = "pgrep -fl %s | grep -v %s" % (re_name, os.getpid())
        logger.info("Extracting processes by name regex: %s" % cmd)
        return self._execute_ps(cmd)


    def _is_text_file(self, file_name):
        """ Return True if file is 'text file', False otherwise

            Calls UNIX 'file' command
        """
        if file_name in self._known_logs:
            # Very expensive to run 'file' command, so we avoid it if log was already evaluated
            log_type = self._known_logs[file_name]
            logger.debug("File: %s was previously discovered to be: %s" % (file_name, log_type))
            if LOG_TYPE_TEXT == log_type:
                return True
            elif LOG_TYPE_BINARY == log_type:
                return False
            elif LOG_TYPE_EMPTY != log_type:
                raise ProcessLogsException("Invalid log type: %s for log: %s" % (log_type, file_name))

        logger.debug("Running 'file' command to detect if: %s is a text file" % file_name)
        cmd = "file -i %s" % file_name
        try:
            result = self._execute(cmd)
        except ProcessLogsException, e:
            if 'No such file or directory' in str(e):
                # Logs are transitory so, it's ok if we cannot find them
                logger.debug("Unable to find file: %s when analyzing type" % file_name)
                return False
            else:
                raise

        # Ok, let's analyze 'file' results
        # Examples:
        # /kafka-logs/__consumer_offsets-24/00000000000000000000.log: application/x-empty; charset=binary
        # /logs/state-change.log: text/plain; charset=us-ascii
        if 'x-empty' in result:
            logger.debug("File: %s is still EMPTY" % file_name)
            self._known_logs[file_name] = LOG_TYPE_EMPTY
            return False
        elif ': text' in result:
            logger.debug("File: %s is TEXT" % file_name)
            self._known_logs[file_name] = LOG_TYPE_TEXT
            return True
        else:
            logger.debug("File: %s is NOT TEXT" % file_name)
            self._known_logs[file_name] = LOG_TYPE_BINARY
            return False


    def _get_files_by_pid(self, pid, re_log_filter):
        """ Parse /proc/<pid>/fd and extract 'logs' by applying 'log_filter'
        """
        log_files = []

        cmd = "ls -l /proc/%d/fd" % pid
        try:
            result = self._execute(cmd)
            if not result:
                # Process are transitory so, it's ok if we cannot find them in /proc
                logger.debug("Unable to find process: %d" % pid)
                return []
        except ProcessLogsException, e:
            if 'No such file or directory' in str(e):
                # Process are transitory so, it's ok if we cannot find them in /proc
                logger.debug("Unable to find process: %d" % pid)
                return []
            else:
                raise
  
        # We only need the last part from:
        # lr-x------. 1 zookeeper zookeeper 64 May 28 18:06 9 -> /usr/lib/zookeeper/zookeeper-3.4.5-cdh5.7.0.jar
        all_files = [_.split()[-1] for _ in result.split('\n')]

        # + only names that match 'log filter'
        # + remove duplicates (same files can be 'listened on' on multiple descriptors
        log_files = list(set([_ for _ in all_files if re_log_filter.search(_)]))

        # + Only allow 'text' files (as 'logs' should be text files)
        text_log_files = [_ for _ in log_files if self._is_text_file(_)]

        return text_log_files


    def _extract_logs(self, process_info, log_filter):
        """ Extract logs for each 'process' in 'process_info'
        """
        for i, proc in enumerate(process_info):
            process_info[i]['logs'] = self._get_files_by_pid(proc['pid'], log_filter)
            logger.info("Analyzing process: %s [pid: %d]. Identified: %d logs" % \
                (proc['cmd'], proc['pid'], len(process_info[i]['logs'])))

        return process_info


    def _get_host_names(self):
        """ Get host name(s) by various means, so that to discard them from 'short log names'
                hostname
                hostname -f
                uname -n

            Running actual UNIX commands here so that can be run remotely over ssh
            Also, should only be run once
        """
        host_cmds = ['hostname -f', 'hostname', 'uname -n']
        host_names = []

        for cmd in host_cmds:
            host_names.append(self._execute(cmd))

        # Add ip addresses (using hostname -f as a baseline)
        host_names.append(socket.gethostbyname(host_names[0]))

        # And various 'local hosts' for completeness 
        host_names.append('127.0.0.1')
        host_names.append('localhost.localdomain')
        host_names.append('localhost')

        return host_names


    def _extract_short_log_name(self, log_name):
        """ Extract 'short' log name, by doing away with meaningless parts, such as hostname or dates

            Inspired by super verbose impala's logs
        """
        log_name = os.path.basename(log_name)

        # Strip host names ('longer' host names should go first)
        for host in self._host_names:
            log_name = log_name.replace(host, '')

        # Drop numbers and special symbols
        log_name = RE_REMOVE_NON_ESSENTIAL.sub('', log_name)

        # Transform '..'s to '.'s etc
        for pat in ('.', '-', '_', '*'):
            log_name = re.sub("\%s{2,}" % pat, pat, log_name)

        # Remove non-essential symbols if they are 'last'
        log_name = RE_LAST_NON_ESSENTIAL.sub('', log_name)

        return log_name


    def _key_by_log(self, process_info):
        """ Re-key data by 'log name' (as ultimately, we need 'a list of (unique) logs')

            Transform: [{'cmd': ..., 'logs': [...], 'pid': ...}, ...]
            into: {
                'log': {
                    'processes': [
                        {'pid': ..., 'cmd': ...},
                        {'pid': ..., 'cmd': ...},
                    ],
                    'log_short': ...,
                    'label': ...,
                    'cmd_short': ...
                }, 
                ...
            }

            setup: Additional log metadata (see: by_pid(), by_name() description)
        """
        keyed_by_log = {}
        setup = self._setup

        # Create 'initial' structure
        for proc in process_info:
            for log in proc['logs']:
                if log not in keyed_by_log:
                    keyed_by_log[log] = {
                        'processes': [],
                        'color': setup.get_color(log),
                        'format': setup.get_format(log),
                        'label': setup.get_label(log),
                        'log_short': self._extract_short_log_name(log),
                    }

                keyed_by_log[log]['processes'].append({'pid': proc['pid'], 'cmd': proc['cmd']})

        # Construct log 'labels' that require post-processing:
        for log in keyed_by_log:
            cmds = keyed_by_log[log]['processes']
            keyed_by_log[log]['cmd_short'] = cmds[0]['cmd'] if 1 == len(cmds) else '[proc: %d]' % len(cmds)

            # If user did not supply a label, set it to log 'short name'
            if not keyed_by_log[log]['label']:
                keyed_by_log[log]['label'] = keyed_by_log[log]['log_short']

        return keyed_by_log


    def _get(self, method, search_key, log_filter):
        """ 'Main' method: get 'process logs' data, while accounting for 'refresh interval'

             method:     'pid', 'name'
             search_key: Appropriate method 'search key' (list of pids for 'pid', name regex for 'name')
             log_filter: Regex to filter log names
        """
        assert method in ALLOWED_METHODS and search_key
        get_call = self._get_process_info_by_pids if METHOD_PID == method else self._get_process_info_by_name

        # Search processes for (pid or name) and return (pid, full_cmd)
        process_data = get_call(search_key)

        # Get process logs by searching through /proc/<pid>/fd
        re_log_filter = re.compile(log_filter) if log_filter else RE_DEFAULT_LOG_NAME_FILTER
        self._process_info = self._extract_logs(process_data, re_log_filter)

        # Transform 'process view' into 'log view' (as we care mostly about logs)
        self._log_info = self._key_by_log(self._process_info) 

        return self._log_info


    ###########################################################################
    # PROPERTIES
    ###########################################################################

    @property
    def process_info(self):
        return self._process_info


    @property
    def log_info(self):
        return self._log_info


    ###########################################################################
    # PUBLIC ROUTINES
    ###########################################################################

    def by_pid(self, pids, log_filter=None):
        """ Get 'logs' for the list of pids

            log_filter: Regular expression to select 'log' names
        """
        log_filter = self._log_filter if not log_filter else log_filter
        logger.debug("Extracting process logs for pids: %s, filter: %s" % (pids, log_filter))

        pids = [pids] if not isinstance(pids, (list, tuple)) else pids

        log_info = self._get(METHOD_PID, pids, log_filter)
        return log_info


    def by_name(self, name, log_filter=None):
        """ Get 'logs' for the specified process 'name pattern'

            log_filter: Regular expression to select 'log' names
        """
        log_filter = self._log_filter if not log_filter else log_filter
        logger.debug("Extracting process logs for name pattern: %s, filter: %s" % (name, log_filter))

        log_info = self._get(METHOD_NAME_REGEX, name, log_filter)
        return log_info
