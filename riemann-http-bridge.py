#!/usr/bin/env python
import os
import sys
import time
import json
import fcntl
import optparse

import bottle

import bernhard

# Daemonizing library - implements unix daemon functionality nicely
# http://pypi.python.org/pypi/python-daemon/
# Ubuntu: python-daemon
import daemon

# Parse command line arguments
parser = optparse.OptionParser()
parser.add_option("--riemann-host", dest="riemann_host", default="localhost", help="Host that Riemann is running on")
parser.add_option("--riemann-port", dest="riemann_port", default=5555, help="Port that Riemann is running on")
parser.add_option("--bind-port", dest="local_port", default=8080, help="Port that for the Bridge to run on")
parser.add_option("--max-age", dest="max_age", default=10, help="Maximum Riemann event age returned")
parser.add_option("--log-dir", dest="log_directory", default=".", help="Directory for where logs should end up")
parser.add_option("--foreground", dest="foreground", action='store_true', default=False, help="Don't daemonize")
parser.add_option("--debug", dest="debug", action='store_true', default=False, help="Increase logger verbosity")
(options, args) = parser.parse_args()

riemann = bernhard.Client(host=options.riemann_host, port=options.riemann_port, transport=bernhard.TCPTransport)

bridge = bottle.Bottle()

pidpath = './bridge.pid'

class PidFile(object):
    """Context manager that locks a pid file.  Implemented as class
    not generator because daemon.py is calling .__exit__() with no parameters
    instead of the None, None, None specified by PEP-343."""

    def __init__(self, path):
        self.path = path
        self.pidfile = None

    def __enter__(self):
        self.pidfile = open(self.path, "a+")
        try:
            fcntl.flock(self.pidfile.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except IOError:
            raise SystemExit("Already running according to " + self.path)
        self.pidfile.seek(0)
        self.pidfile.truncate()
        self.pidfile.write(str(os.getpid()))
        self.pidfile.flush()
        self.pidfile.seek(0)
        return self.pidfile

    def __exit__(self, exc_type=None, exc_value=None, exc_tb=None):
        try:
            self.pidfile.close()
        except IOError as err:
            # ok if file was just closed elsewhere
            if err.errno != 9:
                raise
        os.remove(self.path)


@bridge.get('/ping')
def ping():
    event = {}
    event['service'] = 'monitoring-bridge'
    event['state'] = 'ok'
    event['description'] = 'HTTP to Riemann Bridge'
    event['ttl'] = 600
    event['host'] = 'http_pinger'
    event['tags'] = ['nonotify']

    try:
        riemann.send(event)
        results = riemann.query("'(service = \"monitoring-bridge\")'")
        event_age = time.time() - results[0].event.time

        if event_age > options.max_age:
            raise RuntimeError("Event Age returned > %s: %s" % (options.max_age, event_age))

        response = {'event_age': event_age}
        for field in event.keys():
            response[field] = str(getattr(results[0], field))
        
        return json.dumps(response)
    except RuntimeError as e:
        with open(os.path.join(options.log_directory, 'bridge.log'), 'a+') as fh:
            fh.write("EVENT AGE ERROR: " + str(e))
        bottle.abort(500, "Riemann Slow to Process Events")
    except Exception as e:
        with open(os.path.join(options.log_directory, 'bridge.log'), 'a+') as fh:
            fh.write("ERROR: " + str(e))
        bottle.abort(500, "Riemann Unavailable")


if __name__ == "__main__":
    if len(args) == 0 or 'start' in args:
        if options.foreground:
            bridge.run(host='0.0.0.0', port=options.local_port, debug=options.debug, reloader=options.debug)
        else:
            try:
                with daemon.DaemonContext(working_directory=".", pidfile=PidFile(pidpath)):
                    bridge.run(host='0.0.0.0', port=options.local_port, debug=options.debug, reloader=options.debug)
            except (Exception, SystemExit) as e:
                with open(os.path.join(options.log_directory, 'bridge.log'), 'a+') as fh:
                    fh.write(str(e) + "\n")
    elif 'stop' in args:
        try:
            with open(pidpath) as ph:
                pid = ph.read()
                os.kill(int(pid), 15)
        except IOError as e:
            if e.errno == 2:
                raise SystemExit("Pidfile not found - is the process running?")
            else:
                raise e