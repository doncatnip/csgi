from .core import deepcopydict

from gevent.event import Event, AsyncResult
from gevent.queue import Queue

from gevent import spawn

from uuid import uuid4 as uuid

import logging
log = logging.getLogger(__name__)

class LongPoll:

    class Connection:
        def __init__( self, env, connections, handler, timeout ):
            self.ack_timeout = timeout
            self.ack_done = Event()
            self.ack_id = None
            self.connections = connections
            self.handler = handler
            self.server_event_queue = Queue()
            self.client_event_queue = Queue()
            self._id = uuid().hex

            self.env = deepcopydict( env )
            self.env['connection'] = self

            spawn( self._kill_idle )
            spawn\
                ( self.handler
                , self.env
                , lambda: self.client_event_queue
                , self.server_event_queue.put )


        def _check_next( self, confirm_ID ):
            result = self.server_event_queue.get()
            self.ack_id = confirm_ID
            self.current_result.set( (confirm_ID, result ) )
            self._kill_idle()

        def next( self, confirm_ID, current_ID ):
            if confirm_ID == self.ack_id:
                self.ack_id = None
                self.ack_done.set()
                self.current_result = AsyncResult()
                spawn( self._check_next, current_ID )

            result = self.current_result.get( )
            return result

        def emit( self, event ):
            self.client_event_queue.put( event )

        def _kill_idle( self ):
            self.ack_done.clear()
            self.ack_done.wait( timeout=self.ack_timeout )
            if not self.ack_done.isSet():
                self.close()


        def close( self ):
            self.client_event_queue.put( StopIteration )
            self.server_event_queue.put( StopIteration )
            del self.connections[ self._id ]


    def __init__( self, handler, ack_timeout=20 ):
        self.handler = handler
        self.connections = {}
        self.ack_timeout = ack_timeout

    def connect( self, env, read, write ):
        for request in read():
            connection = self.Connection( env, self.connections, self.handler, self.ack_timeout )
            self.connections[ connection._id ] = connection
            write( (connection._id, self.ack_timeout) )

    def next( self, env, read, write ):
        current_ID = env['rpc']['requestID']
        for (args,kwargs) in read():
            (connection_ID,confirm_ID) = args
            connection = self.connections[connection_ID]

            result = connection.next( confirm_ID, current_ID )
            write( result )

    # should be sent as notification
    def emit( self, env, read, write ):
        for (args,kwargs) in read():
            (connection_ID,event) = args
            connection = self.connections[connection_ID]
            connection.emit( event )


class Call:
    
    def __init__( self, resource, include_env=True ):
        self.resource = resource
        self.include_env = include_env

    def __call__( self, env, read, write ):
        for (args, kwargs) in read():
            if self.include_env:
                args = list(args)
                args.insert( 0, env )
                
            result = self.resource( *args, **kwargs )
            write( result )

