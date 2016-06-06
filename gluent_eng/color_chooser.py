#! /usr/bin/env python
""" ColorChooser: 'Color control' module - chose colors and register colors chosen
"""

import logging

from termcolor import colored


###############################################################################
# EXCEPTIONS
###############################################################################


###############################################################################
# CONSTANTS
###############################################################################

# Appropriate 'foreground' colors with empty background
FG_COLORS = ('green', 'yellow', 'blue', 'magenta', 'cyan')
 
# Appropriate 'background' colors with 'grey' foreground
BG_COLORS = ('green', 'yellow', 'blue', 'magenta', 'cyan', 'white')


###############################################################################
# LOGGING
###############################################################################
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler()) # Disabling logging by default


class ColorChooser(object):
    """ Return colorterm 'colors' that have not been used yet (or used less)
    """

    def __init__(self):
        """ CONSTRUCTOR
        """
        self._colors = [_ for _ in self._make_color_matrix()]
        self._color_idx = 0

        logger.debug("Successfully initialized ColorChooser()")


    def _make_color_matrix(self):
        """ Make "eye-pleasing" color matrix
        """
        good_colors = list(FG_COLORS)
        for bg_color in BG_COLORS:
            good_colors.append("grey_on_%s" % bg_color)
        
        return good_colors


    def next(self):
        """ Return next color that either has not ben used or used less than others
        """
        current_color = self._colors[self._color_idx]

        # Get next color
        self._color_idx += 1
        if self._color_idx >= len(self._colors):
            self._color_idx = 0

        logger.debug("Next color chosen: %s" % current_color)
        return current_color


    @staticmethod
    def colorize(txt, color_format):
        """ Return 'txt', colored by 'color_format'
 
            Unlike termcolor.colored() can process complex colors, i.e. 'white_on_red'
        """
        assert color_format

        color_items = color_format.split('_', 1)
        if 2 == len(color_items):
            return colored(txt, color_items[0], color_items[1])
        else:
            return colored(txt, color_items[0])


def colorize(txt, color_format):
    """ Helper shortcut for ColorChooser.colorize()
    """
    return ColorChooser.colorize(txt, color_format)
