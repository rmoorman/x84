import tempfile
import os
#pylint: disable=W0614
#        Unused import from wildcard import
from x84.bbs import *

def banner():
    term = getterminal()
    return term.home + term.normal + term.clear

def redraw(pager, le):
    rstr = u''
    rstr += pager.border()
    rstr += pager.refresh ()
    rstr += le.border ()
    rstr += le.refresh ()
    #rstr += le.fixate ()
    return rstr

def get_ui(ucs=u'', ypos=None):
    term = getterminal()
    pager = Pager(term.height - 2, term.width, 1, 0)
    pager.colors['border'] = term.bold_blue
    pager.glyphs['left-vert'] = pager.glyphs['right-vert'] = u'|'
    pager.update (ucs)
    yloc = pager.visible_bottom if ypos is None else ypos
    # actually, should - 1 for border ?!
    le = ScrollingEditor(term.width, yloc, 0)
    le.glyphs['bot-horiz'] = le.glyphs['top-horiz'] = u'-'
    le.colors['border'] = term.bold_green
    print 'yloc', yloc
    return pager, le

def prompt_commands(pager):
    pager.footer ('q-uit, s-save')
    # todo: prompt

def quit():
    # todo: prompt
    pass

def main(uattr=u'draft'):
    """
    Retreive and store unicode bytes to user attribute keyed by 'uattr';
    """
    session, term = getsession(), getterminal()
    #pager, le = get_ui(
    #        DBProxy('userattr')[session.user.handle].get(uattr, u''), 0)
    test = open(os.path.join(os.path.dirname(__file__),
        'art', 'news.txt')).read().decode('utf8').strip()
    pager, le = get_ui(test)
    xpos = Ansi(pager.content[-1]).__len__()
    dirty = True
    while True:
        if session.poll_event('refresh'):
            pager, le = get_ui(u'\n'.join(pager.content), le.yloc)
            dirty = True
        if dirty:
            echo (banner())
            echo (redraw(pager, le))
            dirty = False
        inp = getch()
        res = le.process_keystroke (inp)
        print repr(inp), repr(res)
        echo (res)
        if le.quit:
            break
        if le.carriage_returned:
            # woak
            break

        #if ch == '/':
            #pager.footer ('q-uit, s-save')
            #ch = getch()
            #if ch in (u'q', 'Q') and quit()
            #    # quit w/o save
            #    return False
            #if process_keystroke(ch):
            #    break
#    editor = '/usr/local/bin/virus'
#    fp, tmppath = tempfile.mkstemp ()
#    nethackrc = session.user.get(sattr, '')
#    length = len(nethackrc)
#    if 0 != length:
#        written = 0
#        while written < length:
#            written += os.write (fp, nethackrc[written:])
#    os.close (fp)
#    lastmod = os.stat(tmppath).st_mtime
#    d = Door(editor, args=(tmppath,))
#    d._TAP = True
#    if 0 == d.run() and os.stat(tmppath).st_mtime > lastmod:
#        # program exited normaly, file has been modified
#        session.user[sattr] = open(tmppath, 'r').fp.read()
#    os.unlink (tmppath)