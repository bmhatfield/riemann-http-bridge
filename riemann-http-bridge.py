#!/usr/bin/env python
import os
import sys
import time
import json
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


def alive(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    else:
        return True


def pidfile(directory=".", create=False, delete=False):
    if create and delete:
        raise ValueError("Cannot both 'create' and 'delete' PID")

    pidpath = os.path.join(directory, 'bridge.pid')
    exists = os.path.isfile(pidpath)

    if exists:
        with open(pidpath, 'r') as pid:
            pid = int(pid.read())
 
        if create and alive(pid):
            raise IOError("%s already exists!" % (pidpath))
        elif delete:
            os.unlink(pidpath)
        elif create:
            with open(pidpath, 'w') as pid:
                pid.write(str(os.getpid()))
            return os.getpid()
        else:
            return pid
    else:
        if create:
            with open(pidpath, 'w') as pid:
                pid.write(str(os.getpid()))
            return os.getpid()
        elif delete:
            raise IOError("%s does not exist!" % (pidpath))
        else:
            return False


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
                with daemon.DaemonContext(working_directory="."):
                    pidfile(create=True)
                    bridge.run(host='0.0.0.0', port=options.local_port, debug=options.debug, reloader=options.debug)
            except Exception as e:
                with open(os.path.join(options.log_directory, 'bridge.log'), 'a+') as fh:
                    fh.write(str(e))

    elif 'stop' in args:
        pid = pidfile()

        if pid and alive(pid):
            try:
                os.kill(pid, 15)
                pidfile(delete=True)
                print "Killed monitoring-bridge (%s)" % (pid)
            except Exception as e:
                print "Unable to kill %s: %s" % (pidfile(), str(e))
        elif pid:
            pidfile(delete=True)
        else:
            print "No such process or PID"
            sys.exit(0)