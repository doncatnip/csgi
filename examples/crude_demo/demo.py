from csgi import    Socket, Listen, Connect, Farm, LazyResource,\
                    env, http, jsonrpc, rpc, event

from csgi.simple import marshal
from csgi.simple.transport import Line as LineTransport

from csgi.http import wsgi
from csgi.daemonize import DaemonContext

from logging import FileHandler

from gevent import spawn, spawn_later

import logging, re



# logger setup

logger = logging.getLogger('')
logger.setLevel( logging.DEBUG )

handler = FileHandler( 'log' )
handler.setFormatter( logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s") )

logger.addHandler(handler)

daemon = DaemonContext( stderr=handler.stream, pidfile='pid' )

# server setup

log = logging.getLogger(__name__)

import testresource


config = {'db_uri':'sqlite:///db.sqlite' }
config['resource'] = resource = LazyResource( testresource, config )
resource.wsgi.werkzeugapp.application.Shorty.init_database()


config['workerclient'] = Connect\
    ( Socket( 'ipc://worker.sock' )
    , LineTransport( marshal.Json( event.Client() ) )
    )

config['worker'] = workserver = Listen\
    ( Socket( 'ipc://worker.sock' )
    , LineTransport( marshal.Json( event.Channel\
            ( { 'workerchannel': resource.Worker }
            ) ) )
    )

services = env.Router\
    ( ( 'service.echo', resource.EchoHandler.echo )
    , ( 'other.echo', resource.EchoHandler.echo )
    , by=env['rpc']['path']
    , each=rpc.Call( env['route']['handler'] )
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

config['server'] = server = Listen\
    ( Socket( 'tcp://localhost:8081')
    , http.Transport\
        ( env.Router\
            ( ( '/', resource.http.Hello )
            , ( re.compile('^(?P<approot>\/wsgi/simple).*$')
              , wsgi.Server( resource.wsgi.SimpleApp )
              )
            , ( re.compile('^(?P<approot>\/wsgi/werkzeug).*$')
              , wsgi.Server( resource.wsgi.werkzeugapp.application.Shorty )
              )
            , ( '/service/jsonrpc', http.Method( POST=jsonservice ) )
            , ( '/pubsub/longpoll/jsonrpc', http.Method( POST=pubsub ) )
            , by=env['http']['path']
            , on_not_found=resource.http._404
            )
        , on_handler_fail=resource.http._500
        )
    )

def _print_message( message ):
    log.info( message )

def _clienttest():
    log.info('requesting client')
    client = config['workerclient']()

    channel = client.open( 'workerchannel' )

    channel.absorb( _print_message )

    spawn_later( 1, channel.emit, 'somework' )
    spawn_later( 15, channel.emit, 'stop' )
    spawn_later( 16, client.disconnect )

    client.on_disconnect( lambda: log.info('connection closed') )

server = Farm( server, workserver )
daemon.exit_hooks.append( server.stop )
with daemon:
    spawn_later( 1, _clienttest )
    #import cProfile
    #cProfile.run('server.start()')
    server.start()
