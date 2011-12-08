from csgi import Listener, Socket, LazyResource, Call, env, transport, http, wsgi, jsonrpc, rpc, event

from logging import FileHandler
from daemonize import DaemonContext

import logging, re

# logger setup

logger = logging.getLogger('')
logger.setLevel( logging.DEBUG )


handler = FileHandler( 'log' )
handler.setFormatter( logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s") )

logger.addHandler(handler)

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

services = env.Router\
    ( ( 'service.echo', resource.EchoHandler.echo )
    , ( 'other.echo', resource.EchoHandler.echo )
    , by=env['rpc']['path']
    , each=Call( env['route']['hander'] )
    )

channels = event.Channel\
    ( { 'service.channel': resource.EchoHandler.channel
      , 'other.channel': resource.EchoHandler.channel
      }
    )


jsonservice = jsonrpc.Server( services )
longpoll = rpc.LongPoll( channels )

pubsub = jsonrpc.Server\
    ( env.Router\
        ( ( 'connect', longpoll.connect )
        , ( 'next', longpoll.next )
        , ( 'emit', longpoll.emit )
        , by=env['rpc']['path']
        )
    )

config['server'] = server = Listener\
    ( Socket( 'tcp://localhost:8081')
    , transport.HTTP\
        ( env.Router\
            ( ( '/', resource.http.Hello )
            , ( re.compile('^(?P<approot>\/wsgiapp1).*$')
              , wsgi.Server( resource.http.WsgiApp )
              )
            , ( '/service/jsonrpc', http.Method( POST=jsonservice ) )
            , ( '/pubsub/longpoll/jsonrpc', http.Method( POST=pubsub ) )
            , by=env['http']['path']
            , on_not_found=resource.http._404
            )
        , on_handler_fail=resource.http._500
        )
    )

    
daemon.exit_hooks.append( server.stop )
with daemon:
    server.start()

