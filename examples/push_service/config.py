from gevent import monkey
monkey.patch_all()

from csgi import Socket, Listen, Connect, env, http, jsonrpc, rpc, event
from csgi.daemonize import DaemonContext

from logging import FileHandler

import logging, re

# logger setup

logger = logging.getLogger('')
logger.setLevel( logging.DEBUG )

handler = FileHandler( 'log' )
handler.setFormatter( logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s") )

logger.addHandler(handler)


# server setup

from server.service import push, api
from server import website


# configure API
api = jsonrpc.Server\
    ( env.Router\
        ( ( 'register', api.register )
        , ( 'login', api.login )
        , ( 'update.email', api.update_email )
        , by=env['rpc']['path']
        )
    )

# configure push services
channels = event.Channel\
    ( { 'ping': push.ping
      , 'user.profile': push.userProfile
      }
    )


longpoll = rpc.LongPoll( channels )
events = jsonrpc.Server\
    ( env.Router\
        ( ( 'connect', longpoll.connect )
        , ( 'next', longpoll.next )
        , ( 'emit', longpoll.emit )
        , by=env['rpc']['path']
        )
    )


# configure server

dojo_url = 'http://ajax.googleapis.com/ajax/libs/dojo/1.8.2'  
server = Listen\
    ( Socket( 'tcp://localhost:8081')
    , http.Transport\
        ( env.Router\
            ( ( '/', website.Home( dojo_url ) )
            , ( '/service/api', http.Method( POST=api ) )
            , ( '/service/events', http.Method( POST=events ) )
            , by=env['http']['path']
            , on_not_found=website._404
            )
        , on_handler_fail=website._500
        )
    )

# configure daemon

daemon = DaemonContext( stderr=handler.stream, pidfile='pid' )
daemon.exit_hooks.append( server.stop )

with daemon:
    #import cProfile
    #cProfile.run('server.start()')
    server.start()
