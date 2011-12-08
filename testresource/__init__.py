from gevent import sleep, spawn

class EchoHandler:

    def echo( self, env, arg ):
        return arg

    def channel( self, env, channel ):
        channel.emit( 'Hello from %s !' % channel.name )
        for message in channel:
            spawn( self._echo_response, channel, message )
        # connection closed when no messages are left

    def _echo_response( self, channel, message ):
        sleep(10)
        channel.emit( 'Message received: %s' % message )
