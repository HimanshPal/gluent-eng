#! /usr/bin/env python
""" LinuxCmd: Python interface for running Linux commands
        directly
        with sudo 
        over ssh
"""

import getpass
import logging
import os
import subprocess


###############################################################################
# EXCEPTIONS
###############################################################################
class LinuxCmdException(Exception): pass


###############################################################################
# CONSTANTS
###############################################################################

SSH_DEFAULTS = {
    'BatchMode': 'yes',
    'ConnectTimeout': '3',
    'LogLevel': 'ERROR'
}

# Default shell to run linux commands
DEFAULT_SHELL='bash'

# Execution 'types'
EXE_TYPE_DIRECT = 'direct'
EXE_TYPE_SUDO   = 'sudo'
EXE_TYPE_SSH    = 'ssh'


###############################################################################
# LOGGING
###############################################################################
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler()) # Disabling logging by default


class LinuxCmd(object):
    """ LinuxCmd: 'Linux command' abstraction

        Execute linux commands:
            - directly
            - by user@ sudo
            - by user@host ssh

        Optionally supply 'environment variables'

        Separate out execution results into:
            - stdout
            - stderr
            - returncode
            - success

        Also remember: cmd, exec_type, user, host, etc
    """

    def __init__(self, user=None, host=None, environment=None):
        """ CONSTRUCTOR
        """

        self._cmd = None          # (last) Linux command
        self._environment = environment  # ... environment (extra os vars to use)
        self._user = user                # ... user
        self._host = host                # ... host

        self._exe_type = None     # ... execution 'type' (direct, ssh, sudo)
        self._shell = None        # ... execution 'shell' (bash, ksh, etc)

        self._stdout = None       # ... stdout
        self._stderr = None       # ... stderr
        self._returncode = None   # ... return code
        self._success = None      # ... True|False - whether execution was successful

        logger.debug("LinuxCmd() object successfully initialized")


    ###########################################################################
    # PRIVATE ROUTINES
    ###########################################################################

    def _set_environment(self):
        """ Add/set environment variables for the command to run

            If self._environment is not set, return os.environ
        """
        
        if self._environment:
            logger.debug("Adding environment variables: '%s'" % self._environment)
            environ_copy = os.environ.copy()
            environ_copy.update(self._environment)
            return environ_copy
        else:
            logger.debug("Not requested to add environment variables")
            return os.environ


    def _sshize_by_host_user(self):
        """ Construct self._cmd as 'ssh' with: self._user@self._host

            Return 'sshized' command
        """
        logger.debug("Ssh'izing command: %s to be executed by user: %s on host: %s" % (self._cmd, self._user, self._host))

        ssh_options = " ".join("-o %s=%s" % (k, v) for k, v in SSH_DEFAULTS.items())
        logger.debug("Adding SSH options: %s" % ssh_options)

        ssh_environment = ""
        if self._environment:
            ssh_environment = ";".join("%s=%s" % (k, v) for k, v in self._environment.items()) + ';'
            logger.debug("Adding SSH environment: %s" % ssh_environment)


        ssh_cmd = "ssh -t %s %s@%s '%s %s'" % (ssh_options, self._user, self._host, ssh_environment, self._cmd)
        logger.debug("Ssh cmd: %s" % ssh_cmd)

        return ssh_cmd


    def _sudoize_cmd_by_user(self):
        """ Construct self._cmd as a 'sudo' with self._user

            Return 'sudoized' command
        """

        logger.debug("Sudoizing command: %s to be executed by user: %s" % (self._cmd, self._user))
        sudo_cmd = 'sudo -u %s %s -c "%s"' % (self._user, self._shell, self._cmd)
        logger.debug("Sudo cmd: %s" % sudo_cmd)

        return sudo_cmd


    def _set_cmd_by_type(self):
        """ Determine appropriate command for (host, user) combination (direct, sudo, ssh)

            Sets: self._exe_type, self._cmd
        """

        # Neither 'user' nor 'host' is supplied - it's a 'local' command
        if not self._user and not self._host:
            logger.debug("Both: 'user' and 'host' are empty. Assuming: 'direct command'")
            exe_type = EXE_TYPE_DIRECT

        # 'user' is supplied, but not 'host - it's a 'sudo'
        if self._user and not self._host:
            logger.debug("'user' is supplied, but not host. Assuming: 'sudo'")
            self._exe_type = EXE_TYPE_SUDO
            self._cmd = self._sudoize_cmd_by_user()

        # 'host' is supplied - it's 'ssh'
        if self._host:
            if not self._user:
                self._user = getpass.getuser()
                logger.debug("Extracting current user: %s from the environment" % self._user)

            self._exe_type = EXE_TYPE_SSH
            self._cmd = self._sshize_by_host_user()


    def _add_pipe_fail_to_cmd(self):
        """ Add 'pipe fail' code to self._cmd if 'UNIX pipe' is detected
        """
        if '|' in self._cmd:
            logger.debug("Detected Linux 'pipe'. Prepending 'pipe fail' code")
            self._cmd = "set -e; set -o pipefail; %s" % self._cmd


    def _execute(self):
        """ Run 'linux' command: self._cmd, based on:

            self._environment: Export environment variables: {var: value, ...} before execution
            self._user:        Execute command as a different user (or 'current' user if None)
            self._host:        Execute command on a remote host (or 'localhost' if None)

            Sets:
                self._success
                self._stdout
                self._stderr
                self._returncode

             Note:
                 No attempt is made to make 'command' properly 'pythonic' (i.e. ['ls', '-lt', 'afile'])
                 Instead, we run it simply with (self._shell) shell, aka: shell=True
                 This is mostly to avoid decomposing 'UNIX pipes', vars etc
                 Feel free to tackle if you feel adventurous

            Returns: True if successful execution, False otherwise
        """
        success, stdout, stderr, returncode = None, None, None, None

        logger.debug("Preparing to run UNIX command: %s" % self._cmd)

        # Construct 'actual' command
        self._add_pipe_fail_to_cmd() # Add 'pipe fail' code, if it's a pipe
        self._set_cmd_by_type()      # Adjust command for sudo, ssh etc

        # Ok, let's run the command
        logger.debug("Running UNIX command: %s. Type: %s" % (self._cmd, self._exe_type))
        try:
            process = subprocess.Popen(self._cmd, shell=True, env=self._set_environment(),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            stdout, stderr = process.communicate()
            stdout, stderr = stdout.strip(), stderr.strip()
            if not stderr:
                stderr = None
            returncode = process.returncode

            if 0 == returncode:
                success = True
            else:
                logger.debug("Command: %s returned non-zero return code: %d" % (self._cmd, returncode)) 
                success = False if (returncode < 0 or stderr) else True
                if not stdout:
                    stdout = None
        except OSError, e:
            logger.warning("Command: %s failed to execute. Exception: %s" % (self._cmd, e))
            success = False
            returncode = e.errno
            stdout = None
            stderr = e

        logger.debug("Command: %s execution. Success: %s Stdout: %s Stderr: %s" % \
            (self._cmd, success, stdout, stderr))

        self._success = success
        self._stdout = stdout
        self._stderr = stderr
        self._returncode = returncode

        return success


    ###########################################################################
    # PROPERTIES
    ###########################################################################

    @property
    def cmd(self):
        return self._cmd


    @property
    def environment(self):
        return self._cmd


    @property
    def user(self):
        return self._user


    @property
    def host(self):
        return self._host


    @property
    def shell(self):
        return self._shell


    @property
    def stdout(self):
        return self._stdout


    @property
    def stderr(self):
        return self._stderr


    @property
    def returncode(self):
        return self._returncode


    @property
    def success(self):
        return self._success


    ###########################################################################
    # STATIC METHODS
    ###########################################################################

    @staticmethod
    def add_to_env(var, value):
        """ Add (a.k.a. 'prepend') 'value' to environment variable
            (rather than 'replace')
        """

        if var in os.environ:
            return value + ':' + os.environ[var]
        else:
            return value


    ###########################################################################
    # PUBLIC ROUTINES
    ###########################################################################

    def execute(self, cmd, user=None, environment=None, host=None, shell=DEFAULT_SHELL):
        """ Execute linux command: 'cmd' and store results

            'user': Execute command as different user
                    or 'current user' if None
            'environment': Export environment variables: {var: value, ...}
                           before execution
            'host': Host to execute the command on
                    or 'current host' if None

            Execution matrix:
                user=None, host=None: Execute directly
                user, host=None:      Execute with sudo
                user=None, host:      Execute with ssh, current user
                user, host:           Execute with ssh

            Returns: True if successful status, False otherwise
        """
        if not cmd:
            raise LinuxCmdException("Command is NOT supplied in LinuxCmd.execute()")

        self._cmd = cmd
        if user:
            self._user = user
        if environment:
            self._environment = environment
        if host:
            self._host = host
        if shell:
            self._shell = shell

        self._success = self._execute()

        return self._success
