from gevent import sleep, spawn
import logging
log = logging.getLogger(__name__)

class EchoHandler:

    def echo( self, env, arg ):
        return arg

    def channel( self, env, channel ):
        channel.emit( 'Hello from %s !' % channel.name )
        ping = spawn( self._ping, channel )
        channel.absorb( self._echo_response, channel )
        channel.on_disconnect( ping.kill )

    def _echo_response( self, message, channel ):
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

    def _handle_cmd( self, message, channel ):
        if not message == 'stop':
            channel.emit( 'ok, will do %s' % message )
            self.worker = spawn(getattr(self,message), channel )

        elif self.worker:
            self.worker.kill()
            channel.emit( 'stopped' )

    def __call__( self, env, channel ):
        channel.emit('gimme work !')
        channel.absorb( self._handle_cmd, channel )
        channel.on_close( lambda: self.worker.kill() if self.worker else None )

    def somework(self, channel ):
        while True:
            sleep(5)
            channel.emit( 'still working' )
