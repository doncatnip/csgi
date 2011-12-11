from lockfile.pidlockfile import PIDLockFile
from daemon import DaemonContext as _DaemonContext

import gevent

import sys,os, signal, logging
log = logging.getLogger(__name__)

class DaemonContext( _DaemonContext ):
    def __init__( self, pidfile, **kwargs ):

        argv = list(sys.argv)
        filename = self.filename = os.path.abspath( argv.pop(0) )
        path = os.path.dirname(filename)
        kwargs.setdefault( 'working_directory', path )

        if isinstance( pidfile, basestring ):
            if pidfile[0] != '/':
                pidfile = '%s/pidfile' % path

            pidfile = PIDLockFile( '%s/pid' % path )

        if argv:
            cmd = argv.pop(0)
            if cmd=='stop':
                os.kill( pidfile.read_pid(), signal.SIGTERM )
                sys.exit(0)
            if cmd=='restart':
                os.kill( pidfile.read_pid(), signal.SIGTERM )
                c = 10
                while pidfile.is_locked():
                    c-=1
                    gevent.sleep(1)
                    if not c:
                        raise Exception('Cannot stop daemon (Timed out)')

                # should just work without this - but it does not :/
                cmd = [sys.executable, filename]+argv
                cmd.append('&')
                os.system( ' '.join(cmd) )
                exit(0)

        if pidfile.is_locked():
            sys.stderr.write( 'Daemon seems to be already running\r\n' )
            sys.exit(-1)

        self.exit_hooks = kwargs.get('exit_hooks',[])
        files_preserve = kwargs.pop('files_preserve',[])
        for logger in kwargs.pop('loggers',()):
            for handler in logger.handlers:
                if hasattr( handler, 'stream' ):
                    files_preserve.append( handler.stream )

        self.loggers = []
        filename = os.path.basename( self.filename)

        try:
            from setproctitle import setproctitle
            setproctitle( filename )
        except ImportError:
            import ctypes
            try:
                libc = ctypes.CDLL("libc.so.6")
                libc.prctl(15, filename, 0, 0, 0)
            except:
                pass


        _DaemonContext.__init__( self, pidfile=pidfile, files_preserve=files_preserve, **kwargs )

    def open( self ):

        self.files_preserve =\
            list( tuple(self.files_preserve) + tuple( logger.handler.stream for logger in self.loggers ) )
        _DaemonContext.open( self )
        gevent.reinit()

        ## not reliable w/ gevent, unfortunateley .. use stderr redirect instead
        #log = logging.getLogger('UNHANDLED')
        #sys.excepthook = lambda tp, value, tb:\
        #    log.error( ''.join( traceback.format_exception( tp, value, tb ) ) )

        gevent.signal(signal.SIGTERM, self.run_exit_hooks, signal.SIGTERM, None )

    def run_exit_hooks( self, signal, frame ):
        for hook in self.exit_hooks:
            hook()

