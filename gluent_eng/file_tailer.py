#! /usr/bin/env python
""" FileTailer: File 'tail/cat' interface with optional:
        simple filters, a.k.a. 'grep -P'
        complex filters, a.k.a. break each line into "columns", with each column being a separate 'filter'
"""

import logging
import os.path
import re

from termcolor import colored

from .color_chooser import colorize


###############################################################################
# EXCEPTIONS
###############################################################################

class FileTailException(Exception): pass


###############################################################################
# CONSTANTS
###############################################################################


###############################################################################
# LOGGING
###############################################################################
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler()) # Disabling logging by default


class FileTailer(object):
    """ File "tail" interface
    """

    def __init__(self, file_name, color, full_color, format, label):
        """ CONSTRUCTOR

            file_name:  File name to tail
            color:      ('green', 'red', 'red_on_white', ...) Color output from this file
            full_color: (True/False) Whether to color 'the entire output' or just the label
            format:     (regex, i.e. [(?P<id>[^\]]+)\]: (?P<msg>.*))
                        Line structure, see: http://www.regular-expressions.info/named.html
            label:      File label (usually, file name) to be prepended/colorized
        """

        self._file_name = file_name
        self._color = color
        self._full_color = full_color
        self._format = re.compile(format)
        self._label = colorize("[%s]" % label, self._color)

        self._file_handle = None

        logger.debug("FileTailer() successfully initialized for file: %s" % file_name)


    def __del__(self):
        """ DESTRUCTOR

            Cleanup: Close file handle if opened
        """
        logger.debug("DESTRUCTOR closing open file handle: %s" % self._file_name)
        self._close()


    def _close(self):
        """ Close file
        """
        if self._file_handle:
            logger.info("Closing log file: %s" % self._file_name)
            self._file_handle.close()


    def _open_at(self, file_name, open_at_top):
        """ Open file name either "at the top" or "at_the_end"
        """

        if not os.path.isfile(file_name):
            raise FileTailException("Unable to locate file: %s" % file_name)

        logger.debug("Opening file: %s" % file_name)
        self._file_handle = open(file_name)

        if not open_at_top:
            self._file_handle.seek(0, 2) # Set position to the end of the file


    def _format_line(self, line, line_format):
        """ If the line matches "format", return matched dictionary
            otherwise, return None

            format must include "named" patterns, i.e.:

            [(?P<id>[^\]]+)\]: (?P<msg>.*)
            see: http://www.regular-expressions.info/named.html
        """
        ret = None

        logger.debug("Matching line: %s with format: %s" % (line, line_format.pattern))

        matches = line_format.match(line)

        if matches:
            logger.debug("Line: %s matches format: %s" % (line, line_format.pattern))
            ret = matches.groupdict()
        else:
            logger.debug("Line: %s DOES NOT match format: %s" % (line, line_format.pattern))

        return ret


    def _filter_match(self, parsed_items, filters):
        """ Check if (parsed line) items match user supplied "filters"
            Return True if so, False otherwise
        """
        if not filters:
            logger.debug("Filters not supplied. Passing all through")
            return True

        common_keys = list(set(parsed_items.keys()) & set(filters.keys()))

        if not common_keys:
            msg = "No common keys between 'parsed items': %s and 'filters': %s" % \
                (parsed_items, filters)
            msg += ". Skipping by default"
            logger.debug(msg)
            return False

        logger.debug("Matching filters: %s with 'parsed items': %s on common keys: %s" % \
            (filters, parsed_items, common_keys))
        matches = all([filters[_].search(parsed_items[_]) for _ in common_keys])

        if matches:
            logger.debug('MATCHED on common keys: %s' % common_keys)
        else:
            logger.debug('NOT MATCHED on common keys: %s' % common_keys)

        return matches


    def _highlight_line(self, line, hi_pattern):
        """ Highlight supplied line with (predefined) color and attributes
            Keep the rest of the line colorized based on the actual log
        """
        def colorize_item(item, pattern):
            """ If item matches "pattern" -> "highlight" it
                Otherwise, keep exactly as it is
            """
            if pattern.match(item):
                return colored(item, 'red', attrs=['bold', 'reverse'])
            else:
                return self._color_line(item)

        line_items = hi_pattern.split(line)

        return "".join([colorize_item(_, hi_pattern) for _ in line_items])


    def _color_line(self, line):
        """ Colorize "line" by "color"
        """
        return colorize(line, self._color) if self._full_color else line


    def _process_lines(self, lines, filters, highlight):
        """ Process lines, a.k.a.: filter, highlight and emit them
            based on what the user requested
        """
        logger.debug("Found: %d new lines in file: %s" % (len(lines), self._file_handle.name))

        current_line = ""
        for line in lines:
            line = line.strip()
            logger.debug("Processing line: %s" % line)
            matched_items = self._format_line(line, self._format)

            # If line is not formatted, we treat it as a continuation of previous line
            if not matched_items:
                msg = "Line: %s does not match format: %s" % (line, self._format.pattern)
                msg += "Assuming, it's a continuation of previous line"
                logger.debug(msg)
                current_line += "\n%s" % line
                continue
            else:
                current_line = line

            # Match parsed line items to user suppplied "filters"
            filter_match = self._filter_match(matched_items, filters)

            if filter_match:
                if highlight:
                    current_line = self._highlight_line(current_line, highlight)
                else:
                    current_line = self._color_line(current_line)
            else:
                logger.debug("Line: %s does not match filters: %s. Skipping" % \
                    (current_line, filters))
                current_line = ""
                continue

            # MAIN output of FileTailer
            print "%s %s" % (self._label, current_line)
            current_line = ""


    ###############################################################################
    # PROPERTIES
    ###############################################################################

    @property
    def name(self):
        return self._file_name


    ###############################################################################
    # PUBLIC ROUTINES
    ###############################################################################

    def open(self, open_at_top):
        """ Open file
        """
        if not self._file_handle:
            print "[+ LOG] %s %s" % (self._label, self._color_line("Following log file: %s" % self._file_name))
            # logger.info("Opening log file: %s" % self._file_name)
            self._open_at(self._file_name, open_at_top)


    def close(self):
        """ Close file
        """
        print "[- LOG] %s %s" % (self._label, self._color_line("Unfollowing log file: %s" % self._file_name))
        self._close()


    def tail(self, filters, highlight):
        """ File "tailer"

            1. Read new lines
            2. Match lines by filters and only print 'matched' lines
            3. If 'highlight' is requested, highlight lines if pattern is detected
        """

        # If for whatever reason the file was not open (open() not called) -> force open
        # And go to the end of the file
        if not self._file_handle:
            self._open_at(self._file_name, open_at_top=False)

        logger.debug("Tailing: %s file" % self._file_handle.name)
        where = self._file_handle.tell()
        lines = self._file_handle.readlines()

        if lines:
            self._process_lines(lines, filters, highlight)
        else:
            logger.debug("No new lines in file: %s" % self._file_handle.name)
            self._file_handle.seek(where)
