from gevent import socket, spawn, joinall, sleep

from gevent.event import AsyncResult, Event
from gevent import Timeout

import re
import os


import logging
log = logging.getLogger(__name__)

#TODO: tests; clients; organize to submodules ofc.; stuff

class Undefined:
    pass

def deepcopydict(org):
    '''
    much, much faster than deepcopy, for a dict of the simple python types.
    '''
    out = org.copy()
    for k, v in org.iteritems():
        if isinstance(v, dict):
            out[k] =  deepcopydict(v)
        elif isinstance( v, list):
            out[k] = v[:]

    return out


re_host_tcp = re.compile(r'^(tcp):\/\/([a-z\.]+|([0-9]+\.){3}[0-9]+):([0-9]+)$', re.I)
re_host_ipc = re.compile(r'^(ipc):\/\/(.*)$', re.I)

def parseSocketAddress(address):
    port = None
    m = re_host_tcp.match(address)
    if m:
        (protocol, host, waste, port) = m.groups()
        port = int(port)
    else:
        m = re_host_ipc.match(address)
        if not m:
            raise SyntaxError('%s is not a valid address ( (tcp://host[:port]|ipc://file) is required )' % address)
        (protocol, host) = m.groups()

    return (protocol.lower(), host, port)

class Socket:
    # TODO: move user, group into ipc address query string
    def __init__(self, address, user=None, backlog=255):
        self.listeningsock = None
        self.address = address
        self.backlog = backlog
        self.user = user
        self.connections = set()

        (self.protocol, self.host, self.port) = parseSocketAddress(self.address)

        if self.protocol not in ('ipc', 'tcp'):
            raise SyntaxError('Protocol %s not supported' % (self.protocol))

        if self.protocol == 'ipc':
            self.host = os.path.abspath(self.host)
            self.address = '%s://%s' % (self.protocol, self.host)

    def connect(self):
        if self.protocol == 'ipc':
            gsocket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            gsocket.connect(self.host)

        return Connection(gsocket)

    def accept(self):
        if self.protocol == 'ipc':
            try:
                os.remove(self.host)
            except OSError:
                pass

            #s.bind( self.host )

            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.bind(self.host)
            os.chmod(self.host, 0770)
            if self.user:
                import pwd

                pe = pwd.getpwnam(self.user)
                os.chown(self.host, pe.pw_uid, pe.pw_gid)
        else:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((self.host, self.port))

        s.listen(self.backlog)

        self.listeningsock = s

        log.info("Listening on %s (%s) ..." % (self.address, self))
        exec_count = 0

        while True:
            try:
                connection, addr = self.listeningsock.accept()
                connection = Connection(socket.socket(_sock=connection), self._remove_connection)
                self.connections.add(connection)
                yield (connection, addr)
            except KeyboardInterrupt:
                raise
            except:
                if not self.listeningsock:
                    break
                log.exception('Could not accept a connection...')
                sleep(0.5 * exec_count)
                exec_count += 1
            else:
                log.debug("New connection at %s" % self.address)
                exec_count = 0

    def close(self):
        if self.listeningsock:
            for connection in list(self.connections):
                connection.close()

            s = self.listeningsock
            self.listeningsock = None
            s._sock.close()
            s.close()

            if self.protocol == 'ipc':
                try:
                    os.remove(self.host)
                except OSError:
                    pass

    def _remove_connection(self, connection):
        self.connections.remove(connection)


# this should just behave like a file-like obj
class Connection:
    _has_fileobj = False

    timeout_read = 30

    def __init__(self, gsocket, close_cb=lambda me: None):
        self._sock = gsocket

        self.flush = self.fileobj.flush
        self.write = self.fileobj.write
        self.read = self.fileobj.read

        self.close_cb = close_cb

        # somehow, the file-like obj does not release read locks on clients
        # when connection was closed locally, so we use iteration as workaround
        # which seems to work but ignores readline limit ofc.
        self.readline = self.fileobj.readline
        #fileiter = iter(self.fileobj)
        #self.readline = lambda limit=16384: fileiter.next()

    @property
    def fileobj(self):
        self.fileobj = self._sock.makefile()
        self._has_fileobj = True
        return self.fileobj

    """
    def readline(self, limit=16384):
        while not self.fileobj.closed:
            try:
                with Timeout(self.timeout_read):
                    return self.fileobj.readline(limit)
            except:
                pass
        return ''
    """

    def __iter__(self):
        return self.fileobj.__iter__()

    def readlines(self, hint=None):
        self.readlines = self.fileobj.readlines
        return self.readlines(hint)

    def close(self):
        if self._has_fileobj:
            try:
                self.fileobj.close()
            except socket.error:
                pass
        try:
            self._sock.shutdown(socket.SHUT_RDWR)
            self._sock._sock.close()
            self._sock.close()
        except socket.error:
            pass

        self.close_cb(self)

class Connect:

    def __init__(self, socket, handler, create_env=lambda: {}):
        self.socket = socket
        self.handler = handler
        self.create_env = create_env
        self.connections = set()  # TODO the actual pool

    def __call__(self, *args, **kwargs):
        _socket = self.socket.connect()
        env = self.create_env()
        env.update\
            ( { 'socket': self.socket
              , 'connection': _socket
              , 'localclient': {'args': args, 'kwargs': kwargs, 'result': AsyncResult()}
              }
            )

        spawn\
            ( self.handler
            , env
            , _socket
            )

        return env['localclient']['result'].get()


class Listen:
    i = 0

    def __init__(self, socket, handler, create_env=None):
        self.socket = socket
        self.handler = handler
        if not create_env:
            create_env = lambda: {}
        self.create_env = create_env
        self._disconnected = None

    def start(self):
        self._disconnected = Event()
        self.connected = True
        for (connection, address) in self.socket.accept():
            spawn(self._handle_connection, connection, address)

    def _handle_connection(self, connection, address):
        try:
            self.i += 1
            env = self.create_env()
            env.update\
                ( remoteclient={'address': address or ('', '',)}
                , socket=self.socket
                , connection=connection
                )

            self.handler(env, connection)
        except Exception as e:
            if not isinstance(e, socket.error) or e.errno != 32:
                log.exception('Could not handle connection at %s from %s' % (self.socket, address))
            else:
                log.debug('Remote client lost.')
        finally:
            self.i -= 1
            connection.close()
            log.debug('Connection closed, open connections: %s' % self.i)

    def stop(self):
        if not self.connected:
            return
        log.info('Stop listening at %s (%s)' % (self.socket.address, self))
        self.socket.close()

        self._disconnected.set()
        self.connected = False

    def wait_for_disconnect(self):
        return self._disconnected.wait()


class Env:
    # TODO: move NotFound *handling* elsewere
    class NotFound(Exception):
        def __init__(self, what):
            self.what = what
            Exception.__init__(self, what)

    class Router:

        def __init__(self, *handlers, **params):
            self.handler = []
            self.named_routes = {}

            routes = set()

            for i in range(len(handlers)):
                (key, handler) = handlers[i]
                if key in routes:
                    raise SyntaxError('Routes must be unique')

                routes.add(key)
                if isinstance(key, basestring):
                    self.named_routes[key] = handler
                else:
                    if hasattr(key, 'match'):
                        key = key.match
                    if not callable(key):
                        raise SyntaxError('Invalid route - must be a string, callable or an object with a match() method')
                    self.handler.append((key, handler))

            self.by = params.pop('by')
            self.each = params.pop('each', None)
            self.on_not_found = params.pop\
                ( 'on_not_found'
                , lambda env, read, write: log.error('route not found .. env: %s' % (env,))
                )

            if params:
                raise SyntaxError('Invalid keyword arguments: %s' % params.keys())

        def __call__(self, env, read, write):
            value = self.by(env)
            handler = self.named_routes.get(value, None)

            env['route'] = {'path': value}

            if not handler:
                for key, handler_ in self.handler:
                    match = key(value)
                    if match:
                        groups = match.groupdict()
                        if groups:
                            env['route'].update(groups)

                        handler = handler_
                        break

            if not handler:
                self.on_not_found(env, read, write)
                return

            if self.each:
                env['route']['handler'] = handler
                self.each(env, read, write)
            else:
                try:
                    handler(env, read, write)
                except Env.NotFound:
                    self.on_not_found(env, read, write)

    def __call__(self, *args, **kwargs):
        value = args[0]
        for part in self.path:
            value = value[part]
        if callable(value):
            return value(*args, **kwargs)
        else:
            return value

    def __init__(self, path=None, name=None):
        if path is None:
            self.path = ()
        else:
            self.path = path + (name,)

    def __getitem__(self, name):
        return Env(self.path, name)

    def set(self, updater, handler):
        return Env.Setter(self.path, updater, handler)

    class Setter:
        def __init__(self, path, updater, handler):
            self.path = path
            self.updater = updater
            self.handler = handler

        def __call__(self, env, r, w):
            env_to_update = env
            value = self.updater(env)

            if self.path:
                for part in self.path[:-1]:
                    env_to_update = env_to_update[part]
                env_to_update[self.path[-1]] = value
            else:
                env = value

            self.handler(env, r, w)


class ArgRouter:

    def __init__(self, *handler):
        self.handler = {}
        handler = list(handler)
        lastValue = handler.pop(0)

        i = 0
        while handler:
            value = handler.pop(0)
            if i % 2 == 0:
                self.handler[lastValue] = value

            lastValue = value
            i += 1

    def __call__(self, env, read, write):
        for data in read():
            args, kwargs = data
            args = list(args)
            path = args.pop(0)

            rpc_env = env.get('rpc', None)
            if rpc_env is None:
                env['rpc'] = {'path': path}
            else:
                env['rpc']['path'] = path

            self.handler[path](env, lambda: ((args, kwargs),), write)


from inspect import isclass

class LazyResource:
    def __init__(self, module, *args, **kwargs):
        self.module = module
        self.loaded = {}
        self.args = args
        self.kwargs = kwargs

        if hasattr(module, 'init'):
            module.init(*args, **kwargs)

    def __getattr__(self, name):
        if not name in self.loaded:
            try:
                __import__('%s.%s' % (self.module.__name__, name))

                value = LazyResource\
                    ( getattr(self.module, name)
                    , *self.args, **self.kwargs
                    )

            except ImportError:
                if not hasattr(self.module, name):
                    raise

                value = getattr(self.module, name)
            if isclass(value):
                value = value(*self.args, **self.kwargs)

            self.loaded[name] = value

        return self.loaded[name]

class Farm:
    def __init__(self, *servers):
        self.servers = servers

    def start(self):
        jobs = []
        for server in self.servers:
            jobs.append(spawn(server.start))

        joinall(jobs)

    def stop(self):
        for server in self.servers:
            server.stop()
