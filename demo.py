from csgi import    Listener, Socket, ConnectionPool, Farm, LazyResource, Call,\
                    env, transport, http, wsgi, jsonrpc, rpc, event, marshal

from logging import FileHandler
from daemonize import DaemonContext

from gevent import spawn, spawn_later

import logging, re

# logger setup

logger = logging.getLogger('')
logger.setLevel( logging.DEBUG )

handler = FileHandler( 'log' )
handler.setFormatter( logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s") )

logger.addHandler(handler)

# daemon = DaemonContext( stderr=handler.stream, pidfile='pid' )

# server setup

import testresource

config = {'some':'config'}
config['resource'] = resource = LazyResource( testresource, config )


config['workerclient'] = ConnectionPool\
    ( Socket( 'ipc://worker.sock' )
    , transport.Line( marshal.Json( event.Client() ) )
    )

config['worker'] = workserver = Listener\
    ( Socket( 'ipc://worker.sock' )
    , transport.Line( marshal.Json( event.Channel\
            ( { 'workerchannel': resource.Worker }
            ) ) )
    )

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

def _clienttest():
    client = config['workerclient']()
    channel = client.open( 'workerchannel' )

    spawn_later( 5, channel.emit, 'somework' )
    for message in channel:
        print message


spawn( _clienttest )

server = Farm( server, workserver )
"""
daemon.exit_hooks.append( server.stop )
with daemon:
"""
try:
    server.start()

finally:
    server.stop()

