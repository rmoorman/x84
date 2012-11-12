#!/usr/bin/env python
"""
Command-line launcher and main event loop for x/84
"""
# Please place _ALL_ Metadata here. No need to duplicate this
# in every .py file of the project -- except where individual scripts
# are authored by someone other than the authors, licensing differs, etc.
__author__ = "Johannes Lundberg, Jeffrey Quast"
__copyright__ = "Copyright 2012"
__credits__ = ["Johannes Lundberg", "Jeffrey Quast",
               "Wijnand Modderman-Lenstra", "zipe", "spidy", "Mercyful Fate"]
__license__ = 'ISC'
__version__ = '1.0rc1'
__maintainer__ = 'Jeff Quast'
__email__ = 'dingo@1984.ws'
__status__ = 'Development'


def main():
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
    import os

    import x84.terminal
    import x84.bbs.ini
    import x84.bbs.userbase
    import x84.telnet

    lookup_bbs = ('/etc/x84/default.ini',
                  os.path.expanduser('~/.x84/default.ini'))
    lookup_log = ('/etc/x84/logging.ini',
                  os.path.expanduser('~/.x84/logging.ini'))
    try:
        opts, tail = getopt.getopt(sys.argv[1:], ":", ('config', 'logger',))
    except getopt.GetoptError, err:
        sys.stderr.write('%s\n' % (err,))
        return 1
    for opt, arg in opts:
        if opt in ('--config',):
            lookup_bbs = (arg,)
        elif opt in ('--logger',):
            lookup_log = (arg,)
    if len(tail):
        sys.stderr.write('Unrecognized program arguments: %s\n' % (tail,))

    # load/create .ini files
    x84.bbs.ini.init(lookup_bbs, lookup_log)

    # initilization
    x84.bbs.userbase.digestpw_init(
        x84.bbs.ini.CFG.get('system', 'password_digest'))

    # start telnet server
    telnetd = x84.telnet.TelnetServer((
        x84.bbs.ini.CFG.get('telnet', 'addr'),
        x84.bbs.ini.CFG.getint('telnet', 'port'),),
        x84.terminal.on_connect,
        x84.terminal.on_naws)

    try:
        # begin main event loop
        _loop(telnetd)
    except KeyboardInterrupt:
        # catch ^C, close all sockets,
        for fileno, client in telnetd.clients.items()[:]:
            client.sock.close()
            del telnetd.clients[fileno]
    finally:
        raise SystemExit


def _loop(telnetd):
    """
    Main event loop. Never returns.
    """
    # pylint: disable=R0912,R0914,R0915
    #         Too many branches (15/12)
    #         Too many local variables (24/15)
    #         Too many statements (73/50)
    import logging
    import select
    import socket
    import time

    import x84.terminal
    import x84.bbs.ini
    import x84.telnet
    import x84.db

    logger = logging.getLogger()
    logger.info('listening %s/tcp', telnetd.port)
    timeout = x84.bbs.ini.CFG.getint('system', 'timeout')
    fileno_telnetd = telnetd.server_socket.fileno()
    locks = dict()
    # main event loop
    while True:
        # close deactivated clients
        for fileno, client in [(fno, clt) for (fno, clt) in
                               telnetd.clients.items() if not clt.active][:]:
            del telnetd.clients[fileno]
            for (clt, pipe, lck) in x84.terminal.terminals():
                if client == clt:
                    pipe.send(('exception', (x84.bbs.exception.Disconnect())))
                    break
            client.sock.close()
            logger.debug('%s: deleted', client.addrport())

        # poll all telnet clients for send
        recv_list = set([fileno_telnetd] + telnetd.clients.keys())

        # try to send all waiting data, marking clients for
        # deactivation that have eof/ otherwise adding their
        # ipc pipes to recv_list.
        for client, pipe, lock in x84.terminal.terminals():
            if not lock.acquire(False):
                logger.debug('%s: locked', client.addrport())
                continue
            if client.active:
                # poll subprocess event pipe
                recv_list.add(pipe.fileno())
                if client.send_ready():
                    try:
                        client.socket_send()
                    except x84.bbs.excpetion.ConnectionClosed, err:
                        logger.debug('%s ConnectionClosed(%s).',
                                     client.addrport(), err)
                        recv_list.remove(client.sock.fileno())
                        client.deactivate()
            lock.release()

        # poll new connections, telnet client input, session pipe input,
        rlist, slist, elist = select.select(recv_list, [], [], 1)

        # accept new connections,
        if fileno_telnetd in rlist:
            rlist.remove(fileno_telnetd)
            try:
                sock, address_pair = telnetd.server_socket.accept()
                if telnetd.client_count() > telnetd.MAX_CONNECTIONS:
                    sock.close()
                    logger.error('refused new connect; maximum reached.')
                else:
                    # accept & instantiate new client
                    client = x84.telnet.TelnetClient(
                        sock, address_pair, telnetd.on_naws)
                    telnetd.clients[client.sock.fileno()] = client
                    telnetd.on_connect(client)
            except socket.error, err:
                logger.error('accept error %d:%s', err[0], err[1],)

        # read in any telnet input
        for fileno in (fno for fno in telnetd.clients if fno in rlist):
            client = telnetd.clients[fileno]
            try:
                client.socket_recv()
            except x84.bbs.exception.ConnectionClosed, err:
                logger.debug('%s: connection closed(%s).',
                             client.addrport(), err)
                # mark for deactivation, removed next poll
                client.deactivate()
                continue

        # accept session event i/o, such as output
        for client, pipe, lock in x84.terminal.terminals():
            # poll about and kick off idle users
            if client.idle() > timeout and lock.acquire(False):
                pipe.send(('exception', x84.bbs.exception.ConnectionTimeout))
                lock.release()
            # send input to subprocess,
            if client.input_ready() and lock.acquire(False):
                inp = client.get_input()
                pipe.send(('input', inp))
                lock.release()
            # aggressively process all session pipe i/o
            has_data = pipe.fileno() in rlist
            while has_data:
                try:
                    event, data = pipe.recv()
                except (EOFError, IOError) as exception:
                    # issue with pipe; sub-process unexpectedly closed
                    logger.exception(exception)
                    x84.terminal.unregister_terminal(client, pipe, lock)
                    pipe.close()
                    client.deactivate()
                    continue

                if event == 'exit':
                    x84.terminal.unregister_terminal(client, pipe, lock)
                    pipe.close()
                    client.deactivate()

                elif event == 'logger':
                    logger.handle(data)

                elif event == 'output':
                    client.send_unicode(ucs=data[0], encoding=data[1])

                elif event == 'global':
                    #pylint: disable=W0612
                    #         Unused variable 'o_lock'
                    for o_client, o_pipe, o_lock in x84.terminal.terminals():
                        if o_client != client:
                            o_pipe.send((event, data,))

                elif event.startswith('db'):
                    # db query-> database dictionary method, callback
                    # with a matching ('db-*',) event. sqlite is used
                    # for now and is quick, but this prevents slow
                    # database queries from locking the i/o event loop.
                    thread = x84.db.DBHandler(pipe, event, data)
                    thread.start()

                elif event.startswith('lock'):
                    # fine-grained lock acquire and release, non-blocking
                    method, stale = data
                    if method == 'acquire':
                        if not event in locks:
                            locks[event] = time.time()
                            logger.debug('%r granted.', (event, data))
                            pipe.send((event, True,))
                        elif (stale is not None
                                and time.time() - locks[event] > stale):
                            logger.error('%r stale.', (event, data))
                            pipe.send((event, True,))
                        else:
                            logger.warn('%r failed.', (event, data))
                            pipe.send((event, False,))
                    elif method == 'release':
                        if not event in locks:
                            logger.error('%r failed.', (event, data))
                        else:
                            del locks[event]
                            logger.debug('%r removed.', (event, data))
                else:
                    assert False, 'unhandled %r' % (event, data)
                try:
                    has_data = (1 == len(select.select
                                        ([pipe.fileno()], [], [], 0)[0]))
                except IOError:
                    has_data = False

if __name__ == '__main__':
    exit(main())
