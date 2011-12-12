from gevent import spawn

class _Channel:
    class Closed( Exception ):
        def __init__( self ):
            Exception.__init__( self, 'Channel is closed' )

    is_open = True

    def __init__( self, env, name, write ):
        self.name = name
        self._write = write
        self.callbacks = []
        self.close_callbacks = []
        self.env = env
    
    def emit( self, event ):
        if not self.is_open:
            raise self.Closed()

        self._write( {'channel': self.name, 'event': event } )

    def run_callbacks( self, event ):
        for (callback,args,kwargs) in self.callbacks:
            callback( event, *args, **kwargs )

    def absorb( self, callback, *args, **kwargs ):
        self.callbacks.append( (callback,args,kwargs) )

    def on_close( self, callback, *args, **kwargs ):
        self.close_callbacks.append( ( callback, args, kwargs ) )

    def close( self ):
        self.is_open = False
        self.callbacks = []
        while self.close_callbacks:
            (callback,args,kwargs) = self.close_callbacks.pop()
            callback( *args, **kwargs )

    def disconnect( self ):
        self.env['connection'].close()

class _ChannelConnector:

    def __init__( self, env, read, write ):
        self.env = env
        self.read = read
        self.write = write
        self.channels = {}
        self.disconnect_callbacks = []

    def open( self, name ):
        channel = self.channels.get( name, None )
        if channel:
            return channel

        channel = _Channel( self.env, name, self.write )
        self.channels[ name ] = channel
        channel.on_close( lambda: self.channels.pop( name ) )
        return channel

    def _keepreading( self ):
        for message in self.read():
            channel = message['channel']
            channel = self.channels.get( channel, None )
            if channel:
                spawn( channel.run_callbacks, message['event'] )

        for channel in list(self.channels.values()):
            channel.close()

        while self.disconnect_callbacks:
            (callback, args, kwargs) = self.disconnect_callbacks.pop()
            callback( *args, **kwargs )

    def disconnect( self ):
        self.env['connection'].close()

    def on_disconnect( self, callback, *args, **kwargs ):
        self.disconnect_callbacks.append( ( callback, args, kwargs ) )

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
            channels[ channel ] = _Channel( env, channel, write )
            handler( env, channels[ channel ] )

        self._keepreading( read, channels )

    def _keepreading( self, read, channels ):
        for message in read():
            channel = message['channel']
            spawn( channels[ channel ].run_callbacks, message['event'] )
            
        for channel in channels.itervalues():
            channel.close()
