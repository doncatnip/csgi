from gevent import sleep, spawn
import logging
log = logging.getLogger(__name__)

class EchoHandler:

    def echo( self, env, arg ):
        return arg

    def channel( self, env, channel ):
        #channel.emit( 'Hello from %s !' % channel.name )
        ping = spawn( self._ping, channel )
        channel.absorb( self._echo_response )
        channel.listen()
        ping.kill()
        log.debug('closing ....')

    def _echo_response( self, channel, message ):
        log.debug('message received: %s' % (message,) )
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


class Worker:
    worker = None

    def _handle_cmd( self, channel, message ):
        if not message == 'stop':
            channel.emit( 'ok, will do %s' % message )
            self.worker = spawn(getattr(self,message), channel )
        elif self.worker:
            self.worker.kill()
            channel.emit( 'stopped' )

    def __call__( self, env, channel ):
        channel.emit('gimme work !')
        channel.absorb( self._handle_cmd )
        channel.listen()
        if self.worker:
            self.worker.kill()

    def somework(self, channel):
        while True:
            sleep(5)
            channel.emit( 'still working' )
