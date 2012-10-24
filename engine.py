#!/usr/bin/env python
"""
command-line launcher and main event loop for x/84
"""
# Please place _ALL_ Metadata here. No need to duplicate this
# in every .py file of the project -- except where individual scripts
# are authored by someone other than the authors, licensing differs, etc.
__author__ = "Johannes Lundberg, Jeffrey Quast"
__copyright__ = "Copyright 2012"
__credits__ = ["Johannes Lundberg", "Jeffrey Quast",
               "Wijnand Modderman-Lenstra", "zipe", "spidy",
               "Mercyful Fate",]
__license__ = 'ISC'
__version__ = '1.0rc1'
__maintainer__ = 'Jeff Quast'
__email__ = 'dingo@1984.ws'
__status__ = 'Development'

def main ():
    """
    x84 main entry point. The system begins and ends here.

    Command line arguments to engine.py:
      --config= location of alternate configuration file
      --logger= location of alternate logging.ini file
    """
    #pylint: disable=R0914
    #        Too many local variables (19/15)
    import getopt
    import sys

    import terminal
    import telnet
    import bbs.ini

    cfg_bbsfile = 'data/default.ini'
    cfg_logfile = 'data/logging.ini'
    try:
        opts, tail = getopt.getopt(sys.argv[1:], ":", ('config', 'logger',))
    except getopt.GetoptError, err:
        sys.stderr.write ('%s\n' % (err,))
        return 1
    for opt, arg in opts:
        if opt in ('--config',):
            cfg_bbsfile = arg
        elif opt in ('--logger',):
            cfg_logfile = arg
    assert 0 == len (tail), 'Unrecognized program arguments: %s' % (tail,)

    # load .ini files
    bbs.ini.init (cfg_bbsfile, cfg_logfile)

    # start telnet server
    addr_tup = (bbs.ini.CFG.get('telnet', 'addr'),
        int(bbs.ini.CFG.get('telnet', 'port')),)
    telnet_server = telnet.TelnetServer (
        address_pair = addr_tup,
        on_connect = terminal.on_connect,
        on_disconnect = terminal.on_disconnect,
        on_naws = terminal.on_naws)

    try:
        # begin main event loop
        _loop (telnet_server)
    except KeyboardInterrupt:
        for client in telnet_server.clients.values():
            client.deactivate ()
        telnet_server.poll ()
        raise SystemExit

def _loop(telnet_server):
    """
    Main event loop. Never returns.
    """
    # pylint: disable=R0912,R0914,R0915
    #         Too many branches (15/12)
    #         Too many local variables (24/15)
    #         Too many statements (73/50)
    import logging
    import time

    import terminal
    import db
    import bbs.ini

    logger = logging.getLogger()
    logger.info ('listening %s/tcp', telnet_server.port)
    client_timeout = int(bbs.ini.CFG.get('session', 'timeout', '1984'))
    locks = dict ()
    # main event loop
    while True:
        # process telnet i/o
        telnet_server.poll ()
        for client, pipe, lock in terminal.terminals():
            if not lock.acquire(False):
                continue
            lock.release ()

            # process telnet input (keypress sequences)
            if client.input_ready() and lock.acquire(False):
                lock.release()
                inp = client.get_input()
                pipe.send (('input', inp))

            # kick off idle users
            if client.idle() > client_timeout:
                logger.info ('%s timeout.', client.addrport())
                pipe.send (('exception', (
                    bbs.exception.ConnectionTimeout, None,)))
                client.deactivate ()
                continue

            if lock.acquire(False):
                # process bbs session i/o
                lock.release ()
                if not pipe.poll ():
                    continue

            # session i/o sent from child process
            try:
                event, data = pipe.recv()
            except EOFError:
                client.deactivate ()
                continue

            if event == 'disconnect':
                client.deactivate ()

            elif event == 'logger':
                logger.handle (data)

            elif event == 'output':
                text, cp437 = data
                if not cp437:
                    client.send_unicode (text)
                    continue
                else:
                    # disguise cp437 as ios8859-1 so bytes remain unmolested
                    bytestring = text.encode('iso8859-1', 'replace')
                    client.send_str (bytestring)

            elif event == 'global':
                #pylint: disable=W0612
                #         Unused variable 'o_lock'
                for o_client, o_pipe, o_lock in terminal.terminals():
                    if o_client != client:
                        o_pipe.send ((event, data,))

            #deprecation,
            #elif event == 'pos':
            #    assert type(data) in (float, int, type(None))
            #    # 'pos' query: 'what is the cursor position ?'
            #    # returns 'pos-reply' event as a callback
            #    # mechanism, data of (None, None) indicates timeout,
            #    # otherwise (y, x) is cursor position ..
            #    thread = terminal.POSHandler(pipe, client, lock,
            #        reply_event='pos-reply', timeout=data)
            #    thread.start ()

            elif event.startswith('db'):
                # db query-> database dictionary method, callback
                # with a matching ('db-*',) event. sqlite is used
                # for now and is quick, but this prevents slow
                # database queries from locking the i/o event loop.
                thread = db.DBHandler(pipe, event, data)
                thread.start ()

            elif event.startswith('lock'):
                # fine-grained lock acquire and release, non-blocking
                method, stale = data
                if method == 'acquire':
                    if not event in locks:
                        locks[event] = time.time ()
                        logger.debug ('(%r, %r) granted.', event, method)
                        pipe.send ((event, True,))
                    elif (stale is not None
                            and time.time() - locks[event] > stale):
                        logger.error ('(%r, %r) stale.', event, method)
                        pipe.send ((event, True,))
                    else:
                        logger.warn ('(%r, %r) failed.', event, method)
                        pipe.send ((event, False,))
                elif method == 'release':
                    if not event in locks:
                        logger.error ('(%s, %s) not acquired.', event, method)
                    else:
                        del locks[event]
                        logger.debug ('(%s, %s) removed.', event, data)

if __name__ == '__main__':
    exit(main ())
