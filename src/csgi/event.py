from gevent import spawn

class _Channel:
    class Closed( Exception ):
        def __init__( self ):
            Exception.__init__( self, 'Channel is closed' )

    is_open = True

    def __init__( self, name, write ):
        self.name = name
        self._write = write
        self.callbacks = []
        self.disconnect_callbacks = []
    
    def emit( self, event ):
        if not self.is_open:
            raise self.Closed()

        self._write( {'channel': self.name, 'event': event } )

    def run_callbacks( self, event ):
        for (callback,args,kwargs) in self.callbacks:
            callback( event, *args, **kwargs )

    def absorb( self, callback, *args, **kwargs ):
        self.callbacks.append( (callback,args,kwargs) )

    def on_disconnect( self, callback, *args, **kwargs ):
        self.disconnect_callbacks.append( ( callback, args, kwargs ) )

    def _disconnect( self ):
        self.is_open = False
        self.callbacks = []
        while self.disconnect_callbacks:
            (callback,args,kwargs) = self.disconnect_callbacks.pop()
            callback( *args, **kwargs )

    def close( self ):
        self._disconnect()


class _ChannelConnector:

    def __init__( self, env, read, write ):
        self.env = env
        self.read = read
        self.write = write
        self.channels = {}

    def open( self, name ):
        channel = self.channels.get( name, None )
        if channel:
            return channel

        channel = _Channel( name, self.write )
        self.channels[ name ] = channel
        channel.on_disconnect( lambda: self.channels.pop( name ) )
        return channel

    def _keepreading( self ):
        for message in self.read():
            channel = message['channel']
            channel = self.channels.get( channel, None )
            if channel:
                spawn( channel.run_callbacks, message['event'] )
        for channel in list(self.channels.values()):
            channel._disconnect()

    def disconnect( self ):
        self.env['socket'].close()

class Client:
    def __call__( self, env, read, write ):
        client = _ChannelConnector( env, read, write )
        env['localclient']['result'].set( client )
        client._keepreading()

class Channel:

    def __init__( self, handlers ):
        self.handlers = handlers

    def __call__( self, env, read, write ):
        channels = {}
        for ( channel, handler) in self.handlers.iteritems():
            channels[ channel ] = _Channel( channel, write )
            handler( env, channels[ channel ] )

        self._keepreading( read, channels )

    def _keepreading( self, read, channels ):
        for message in read():
            channel = message['channel']
            spawn( channels[ channel ].run_callbacks, message['event'] )
            
        for channel in channels.itervalues():
            channel._disconnect()
