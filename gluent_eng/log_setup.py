#! /usr/bin/env python
""" LogSetup: Read 'ptail log' metadata from YAML file or construct if missing
"""

import logging
import os.path
import re
import yaml

from collections import OrderedDict

from .color_chooser import ColorChooser


###############################################################################
# EXCEPTIONS
###############################################################################


###############################################################################
# CONSTANTS
###############################################################################

# Default 'log entry' format
DEFAULT_LOG_ENTRY = '^(?P<text>.*)$'


###############################################################################
# LOGGING
###############################################################################
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler()) # Disabling logging by default


class LogSetup(object):
    """ Manage relevant "log setup" metadata, i.e. colors, formats and labels
    """

    def __init__(self, setup_file):
        """ CONSTRUCTOR
        """
        self._setup = self._read_setup(setup_file) # 'Metadata' from setup file (generic: 'log patterns')
        self._log_meta = {}                        # Final 'log file' metadata  (specific: 'log files')

        # Supporting objects
        self._colors = ColorChooser()  # Chose random colors, if colors are not specified

        logger.debug("Successfully initialized LogSetup() from_file: %s" % setup_file)


    ###########################################################################
    # PRIVATE ROUTINES
    ###########################################################################

    def _ordered_yaml_load(self, stream, Loader=yaml.Loader, object_pairs_hook=OrderedDict):
        """ Load YAML entries in the order they appear in the file
        """
        class OrderedLoader(Loader):
            pass

        def construct_mapping(loader, node):
            loader.flatten_mapping(node)
            return object_pairs_hook(loader.construct_pairs(node))

        OrderedLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_mapping)

        return yaml.load(stream, OrderedLoader)


    def _read_setup(self, setup_file):
        """ Read (YAML) setup file and return contents

            Expected contents:
                log name pattern:
                    color: ...
                    format: ...
                    label: ...
                ...

            All keys are optional
        """
        if not setup_file:
            logger.debug("Setup file (YAML) is not specified. Returning: 'empty setup'")
            return {}

        data = {}
        logger.info("Reading log metadata from config file (YAML): %s" % setup_file)

        if os.path.exists(setup_file):
            with open(setup_file) as f:
                data = self._ordered_yaml_load(f)
        else:
            logger.info("Log metadata config file (YAML): %s does NOT exist" % setup_file)

        logger.debug("Setup data: %s" % data)

        return self._compile_setup_patterns(data)


    def _compile_setup_patterns(self, setup):
        """ Regex compile setup patterns
        """
        return {re.compile(_): setup[_] for _ in setup}


    def _get_setup(self, log_file):
        """ Check if 'relevant' metadata exists in setup for specific log file
            (and return it if it does)

            'Relevant' = log file name matches setup file 'pattern'
            Setup entries are scanned in order and the first match wins

            i.e. 'red' will be chosen below as: /tmp/hive/hive-metadata.log =~ hive

            log_file: /tmp/hive/hive-metadata.log
            setup:
                hive:
                    color: blue
                hive-metadata:
                    color: red
        """
        meta = {}

        for pattern in self._setup:
            if pattern.search(log_file):
                logger.debug("Found pattern: %s for log_file: %s" % (pattern.pattern, log_file))
                meta = self._setup[pattern]
                break

        logger.debug("Metadata for log file: %s is: %s" % (log_file, meta))
        return meta


    def _init_log_entry(self, log_file):
        """ Initialize log entry for a specific log from 'setup' or otherwise
        """
        if log_file not in self._log_meta:
            log_meta = self._get_setup(log_file)

            # + default color
            if 'color' not in log_meta or not log_meta['color']:
                log_meta['color'] = self._colors.next()
                logger.debug("Color for log: %s not specified. Assigning color: %s" % (log_file, log_meta['color']))

            # + default format
            if 'format' not in log_meta or not log_meta['format']:
                log_meta['format'] = DEFAULT_LOG_ENTRY
                logger.debug("Format for log: %s not specified. Assigning format: %s" % (log_file, log_meta['format']))

            # + default label
            if 'label' not in log_meta or not log_meta['label']:
                log_meta['label'] = None # None denotes: 'replacable later'
                logger.debug("Label for log: %s not specified. Assigning 'passthrough' label" % log_file)

            self._log_meta[log_file] = log_meta
            logger.info("Metadata for log: %s -> %s" % (log_file, log_meta))


    ###########################################################################
    # PUBLIC ROUTINES
    ###########################################################################

    def get_color(self, log_file):
        """ Get 'color' for specific log file

            Default: random color
        """
        self._init_log_entry(log_file)
        return self._log_meta[log_file]['color']


    def get_format(self, log_file):
        """ Get 'format' for specific log file

            Default: DEFAULT_LOG_ENTRY
        """
        self._init_log_entry(log_file)
        return self._log_meta[log_file]['format']


    def get_label(self, log_file):
        """ Get 'label' for specific log file

            Default: None (which means it should be replaced later)
        """
        self._init_log_entry(log_file)
        return self._log_meta[log_file]['label']
