from gevent import sleep, spawn
import logging
log = logging.getLogger(__name__)

class EchoHandler:

    def echo( self, env, arg ):
        return arg

    def channel( self, env, channel ):
        channel.emit( 'Hello from %s !' % channel.name )
        ping = spawn( self._ping, channel )

        for message in channel:
            log.debug('message received: %s' % (message,) )
            spawn( self._echo_response, channel, message )

        ping.kill()
        log.debug('closing ....')

    def _echo_response( self, channel, message ):
        sleep(10)
        channel.emit( 'Message received: %s' % message )

    # only one pinging channel needed ofc, pushed data can be arbitrary
    # if no channel is pinging, the connection is closed anyways nn seconds
    # after the next event occured and was not consumed
    def _ping( self, channel ):
        while True:
            sleep(60)
            log.debug('pinging ...')
            channel.emit( 'ping' )
