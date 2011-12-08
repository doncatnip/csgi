from csgi import Listener, Socket, LazyResource, Call, env, transport, wsgi, jsonrpc

from logging import FileHandler
from daemonize import DaemonContext

import logging, re

# logger setup

logger = logging.getLogger('')
logger.setLevel( logging.DEBUG )

handler = FileHandler( 'log' )
handler.setFormatter( logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s") )

logger.addHandler(handler)

log = logging.getLogger(__name__)

daemon = DaemonContext( loggers=(logger,), pidfile='pid' )

# server setup

import testresource

config = {'some':'config'}
config['resource'] = resource = LazyResource( testresource, config )

#config['workerclient'] = ConnectionPool\
#    ( Socket( 'ipc://worker.sock' )
#    , transport.Line( jsonrpc.Client() )
#    )

#config['worker'] = workserver = Listener\
#    ( Socket( 'ipc://worker.sock' )
#    , transport.Line( jsonrpc.Server( resource.Worker ) )
#    )

config['server'] = server = Listener\
    ( Socket( 'tcp://localhost:8081')
    , transport.HTTP\
        ( env.Router\
            ( ( '/', resource.http.Hello )
            , ( re.compile('^(?P<approot>\/wsgiapp1).*$')
              , wsgi.Server( resource.http.WsgiApp )
              )
            , ( '/service/jsonrpc', env.Router\
                    ( ( 'POST', jsonrpc.Server\
                        ( env.Router\
                            ( ( 'service.echo', resource.EchoHandler.echo )
                            , ( 'other.echo', resource.EchoHandler.echo )
                            , by=env['rpc']['path']
                            , each=Call( env['route']['hander'] )
                            )
                        )
                      )
                    , by=env['http']['method']
                    , on_not_found=resource.http._404
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


daemon.exit_hooks.append( server.stop )
with daemon:
    server.start()

