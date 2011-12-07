from proto import Listener, Socket, LazyResource, Call, env, transport, wsgi, jsonrpc

from logging import FileHandler
from lockfile.pidlockfile import PIDLockFile
from daemon import DaemonContext

import gevent, logging, re, signal, sys, os

# daemon stuff to be offloaded later ..

argv = list(sys.argv)
filename = os.path.abspath( argv.pop(0) )
path = os.path.dirname(filename)

pidfile = PIDLockFile( '%s/pid' % path )

if argv:
    cmd = argv.pop(0)
    if cmd=='stop':
        os.kill( pidfile.read_pid(), signal.SIGTERM )
        sys.exit(0)
    if cmd=='restart':
        os.kill( pidfile.read_pid(), signal.SIGTERM )
        c = 10
        while pidfile.is_locked():
            c-=1
            gevent.sleep(1)
            if not c:
                raise Exception('Cannot stop daemon (Timed out)')

        # should just work without this - but it does not :/
        cmd = (sys.executable, filename, '&')
        os.system( ' '.join(cmd) )
        exit(0)

if pidfile.is_locked():
    sys.stderr.write( 'Daemon seems to be already running\r\n' )
    sys.exit(-1)


# logger setup

logger = logging.getLogger('')
logger.setLevel( logging.DEBUG )

handler = FileHandler( 'log' )
handler.setFormatter( logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s") )

logger.addHandler(handler)

log = logging.getLogger(__name__)


# server setup

import testresource

config = {'some':'config'}
config['resource'] = resource = LazyResource( testresource, config )

#config['client'] = ConnectionPool\
#    ( Socket( 'ipc://testsocket' )
#    , transport.HTTP( IOClient() )
#    )

config['server'] = server = Listener\
    ( Socket( 'tcp://localhost:8081')
    , transport.HTTP\
        ( env.Router\
            ( ( '/', resource.http.Hello )
                # usefull for proxying and stuff ;)
            , ( re.compile('^\/wsgiapp(?P<url>([\/\?].*|))$')
              , env['http']['path'].set\
                    ( env['route']['url']
                    , wsgi.Server( resource.http.WsgiApp )
                    )
              )
            , ( '/service', jsonrpc.Server\
                    ( env.Router\
                        ( ( 'service.echo', resource.EchoHandler.echo )
                        , by=env['rpc']['path']
                        , each=Call( env['route']['hander'] )
                        )
                    )
              )
           #  , '/pubsub', socketIO.Server\
           #        ( ( env.Router\
           #            ( ( 'service.subscribe', resource.EchoHandler.pubsub )
           #            , by=env['rpc']['path']
           #            , each=PubSub\
           #                ( env['route']['handler']
           #                )
           #            )
           #          )
           #        )
           #
           #
            , by=env['http']['path']
            , on_not_found=resource.http._404
            )
        , on_handler_fail=resource.http._500
        )
    )

# daemon stuff to be offloaded later

def terminate( signal, frame ):
    server.stop()


daemon = DaemonContext\
    ( files_preserve=[handler.stream]
    , pidfile=pidfile
    )

with daemon:
    gevent.reinit()
    gevent.signal(signal.SIGTERM, terminate, signal.SIGTERM, None )
    server.start()

