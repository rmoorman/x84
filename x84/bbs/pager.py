"""
Pager class for x/84, http://github.com/jquast/x84/
"""
from x84.bbs.ansiwin import AnsiWindow

NETHACK_KEYSET = {
        'refresh': [unichr(12), ],
        'home': [u'y', ],
        'end': [u'n', ],
        'up': [u'k', ],
        'pgup': [u'K', ],
        'down': [u'j', ],
        'pgdown': [u'J', ],
        'exit': [u'q', u'Q', ],
        }

class Pager(AnsiWindow):
    """
    Scrolling ansi viewer
    """
    #pylint: disable=R0904,R0902
    #        Too many public methods (24/20)
    #        Too many instance attributes (11/7)

    def __init__(self, height, width, yloc, xloc):
        """
        Initialize a pager of height, width, y, and x position.
        """
        AnsiWindow.__init__ (self, height, width, yloc, xloc)
        self._xpadding = 1
        self._ypadding = 1
        self._col = 0
        self._row = 0
        self._position = 0
        self._position_last = 0
        self._moved = False
        self._quit = False
        self.content = list ()
        self.keyset = NETHACK_KEYSET
        self.init_keystrokes ()

    @property
    def moved(self):
        """
        Returnes: True if last call to process_keystroke() resulted in
        movement.
        """
        return self._position != self._position_last

    @property
    def quit(self):
        """
        Returns: True if a terminating or quit character was handled by
        process_keystroke(), such as the escape key, or 'q' by default.
        """
        return self._quit

    @property
    def position_last(self):
        """
        Previous position before last move
        """
        return self._position_last

    @property
    def position(self):
        """
        Returns the row in the content buffer displayed at top of window.
        """
        return self._position

    @position.setter
    def position(self, pos):
        #pylint: disable=C0111
        #         Missing docstring
        self._position_last = self.position
        self._position = pos
        # bounds check
        if self._position < 0:
            self._position = 0
        if self._position > self.bottom:
            self._position = self.bottom

    @property
    def visible_content(self):
        """
        Returns content that is visible in window
        """
        return self.content[self.position:self.position + self.visible_height]

    @property
    def visible_bottom(self):
        """
        Returns bottom-most window row that contains content
        """
        if self.bottom < self.visible_height:
            return self.bottom
        return len(self.visible_content) - 1

    @property
    def bottom(self):
        """
        Returns bottom-most position that contains content
        """
        return max(0, len(self.content) - self.visible_height)

    def init_keystrokes(self):
        """
        This initializer sets keys appropriate for navigation.
        override or inherit this method to create a common keyset.
        """
        import x84.bbs.session
        term = x84.bbs.session.getterminal()
        self.keyset['home'].append (term.KEY_HOME)
        self.keyset['end'].append (term.KEY_END)
        self.keyset['pgup'].append (term.KEY_PPAGE)
        self.keyset['pgdown'].append (term.KEY_NPAGE)
        self.keyset['up'].append (term.KEY_UP)
        self.keyset['down'].append (term.KEY_DOWN)
        self.keyset['exit'].append (term.KEY_EXIT)

    def process_keystroke(self, keystroke):
        """
        Process the keystroke received by run method and return terminal
        sequence suitable for refreshing when that keystroke modifies the
        window.
        """
        self._position_last = self._position
        rstr = u''
        if keystroke in self.keyset['refresh']:
            rstr += self.refresh ()
        elif keystroke in self.keyset['up']:
            rstr += self.move_up ()
        elif keystroke in self.keyset['down']:
            rstr += self.move_down ()
        elif keystroke in self.keyset['home']:
            rstr += self.move_home ()
        elif keystroke in self.keyset['end']:
            rstr += self.move_end ()
        elif keystroke in self.keyset['pgup']:
            rstr += self.move_pgup ()
        elif keystroke in self.keyset['pgdown']:
            rstr += self.move_pgdown ()
        elif keystroke in self.keyset['exit']:
            self._quit = True
        else:
            import x84.bbs.session
            x84.bbs.session.logger.info ('unhandled, %r', keystroke
                    if type(keystroke) is not int
                    else x84.bbs.session.getterminal().keyname(keystroke))
        return rstr

    def move_home(self):
        """
        Scroll to top.
        """
        self.position = 0
        if self.moved:
            return self.refresh ()
        return u''

    def move_end(self):
        """
        Scroll to bottom.
        """
        self.position = len(self.content) - self.visible_height
        if self.moved:
            return self.refresh ()
        return u''

    def move_pgup(self, num=1):
        """
        Scroll up ``num`` pages.
        """
        self.position -= (num * (self.visible_height))
        return self.refresh() if self.moved else u''

    def move_pgdown(self, num=1):
        """
        Scroll down ``num`` pages.
        """
        self.position += (num * (self.visible_height))
        return self.refresh() if self.moved else u''

    def move_down(self, num=1):
        """
        Scroll down ``num`` rows.
        """
        self.position += num
        if self.moved:
            return self.refresh ()
        return u''

    def move_up(self, num=1):
        """
        Scroll up ``num`` rows.
        """
        self.position -= num
        if self.moved:
            return self.refresh ()
        return u''

    def refresh_row(self, row):
        """
        Return unicode string suitable for refreshing pager window at
        visible row.
        """
        ucs = (self.visible_content[row]
                if row < len(self.visible_content) else u'')
        return self.pos(row + self.ypadding, self.xpadding) + self.align(ucs)

    def refresh(self, start_row=0):
        """
        Return unicode string suitable for refreshing pager window from
        optional visible content row 'start_row' and downward. This can be
        useful if only the last line is modified; or in an 'insert' operation,
        only the last line need be refreshed.
        """
        import x84.bbs.session
        term = x84.bbs.session.getterminal()
        return u''.join([self.refresh_row(row)
                for row in range(start_row, len(self.visible_content))]
                + [term.normal])

    def update(self, ucs):
        """
        Update content buffer with lines of ansi unicodes as single unit.
        """
        import x84.bbs.output
        self.content = x84.bbs.output.Ansi(ucs).wrap(
                self.visible_width - 1).split('\r\n')
        return self.refresh ()

    def append(self, ucs):
        """
        Update content buffer with additional lines of ansi unicodes.
        """
        import x84.bbs.output
        self.content.extend (x84.bbs.output.Ansi(ucs
            ).wrap(self.visible_width - 1).split('\r\n'))
        return self.move_end() or self.refresh(self.bottom)