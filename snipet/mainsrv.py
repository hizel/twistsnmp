#!/usr/bin/env python

import SocketServer
import BaseHTTPServer
import SimpleHTTPServer
import SimpleXMLRPCServer

import socket, os
from OpenSSL import SSL
from threading import Event, currentThread, Thread, Condition
from thread import start_new_thread as start
from DocXMLRPCServer import DocXMLRPCServer, DocXMLRPCRequestHandler
from xmlrpclib import Binary

import daemonize
import logging
import os
import signal

# static stuff
DEFAULTKEYFILE='cert/localhost-server.key.unsecure'    # Replace with your PEM formatted key file
DEFAULTCERTFILE='cert/localhost-server.crt'  # Replace with your PEM formatted certificate file


class SecureDocXMLRpcRequestHandler(DocXMLRPCRequestHandler):
    """Secure Doc XML-RPC request handler class.
    It it very similar to DocXMLRPCRequestHandler but it uses HTTPS for transporting XML data.
    """
    def setup(self):
        self.connection = self.request
        self.rfile = socket._fileobject(self.request, "rb", self.rbufsize)
        self.wfile = socket._fileobject(self.request, "wb", self.wbufsize)

    def address_string(self):
        "getting 'FQDN' from host seems to stall on some ip addresses, so... just (quickly!) return raw host address"
        host, port = self.client_address
        #return socket.getfqdn(host)
        return host

    def do_POST(self):
        """Handles the HTTPS POST request.
        It was copied out from SimpleXMLRPCServer.py and modified to shutdown the socket cleanly.
        """
        try:
            # get arguments
            data = self.rfile.read(int(self.headers["content-length"]))
            # In previous versions of SimpleXMLRPCServer, _dispatch
            # could be overridden in this class, instead of in
            # SimpleXMLRPCDispatcher. To maintain backwards compatibility,
            # check to see if a subclass implements _dispatch and dispatch
            # using that method if present.
            response = self.server._marshaled_dispatch(data, getattr(self, '_dispatch', None))
        except: # This should only happen if the module is buggy
            # internal error, report as HTTP server error
            self.send_response(500)
            self.end_headers()
        else:
            # got a valid XML RPC response
            self.send_response(200)
            self.send_header("Content-type", "text/xml")
            self.send_header("Content-length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

            # shut down the connection
            self.wfile.flush()
            self.connection.shutdown() # Modified here!

    def do_GET(self):
        """Handles the HTTP GET request.

        Interpret all HTTP GET requests as requests for server
        documentation.
        """
        # Check that the path is legal
        if not self.is_rpc_path_valid():
            self.report_404()
            return

        response = self.server.generate_html_documentation()
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.send_header("Content-length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

        # shut down the connection
        self.wfile.flush()
        self.connection.shutdown() # Modified here!

    def report_404 (self):
        # Report a 404 error
        self.send_response(404)
        response = 'No such page'
        self.send_header("Content-type", "text/plain")
        self.send_header("Content-length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)
        # shut down the connection
        self.wfile.flush()
        self.connection.shutdown() # Modified here!

    def log_request (self, code = '-', size = '-'):
        log.info( self.requestline )



class CustomThreadingMixIn:
    """Mix-in class to handle each request in a new thread."""
    # Decides how threads will act upon termination of the main process
    daemon_threads = True

    def process_request_thread(self, request, client_address):
        """Same as in BaseServer but as a thread.
        In addition, exception handling is done here.
        """
        try:
            self.finish_request(request, client_address)
            self.close_request(request)
        except (socket.error, SSL.SysCallError), why:
            print 'socket.error finishing request from "%s"; Error: %s' % (client_address, str(why))
            self.close_request(request)
        except:
            self.handle_error(request, client_address)
            self.close_request(request)

    def process_request(self, request, client_address):
        """Start a new thread to process the request."""
        t = Thread(target = self.process_request_thread, args = (request, client_address))
        if self.daemon_threads:
            t.setDaemon(1)
        t.start()



class SecureDocXMLRPCServer(CustomThreadingMixIn, DocXMLRPCServer):
    def __init__(self, registerInstance, server_address, keyFile=DEFAULTKEYFILE, certFile=DEFAULTCERTFILE, logRequests=True):
        """Secure Documenting XML-RPC server.
        It it very similar to DocXMLRPCServer but it uses HTTPS for transporting XML data.
        """
        DocXMLRPCServer.__init__(self, server_address, SecureDocXMLRpcRequestHandler, logRequests)
        self.logRequests = logRequests

        # stuff for doc server
        try: self.set_server_title(registerInstance.title)
        except AttributeError: self.set_server_title('default title')
        try: self.set_server_name(registerInstance.name)
        except AttributeError: self.set_server_name('default name')
        if registerInstance.__doc__: self.set_server_documentation(registerInstance.__doc__)
        else: self.set_server_documentation('default documentation')
        self.register_introspection_functions()

        # init stuff, handle different versions:
        try:
            SimpleXMLRPCServer.SimpleXMLRPCDispatcher.__init__(self)
        except TypeError:
            # An exception is raised in Python 2.5 as the prototype of the __init__
            # method has changed and now has 3 arguments (self, allow_none, encoding)
            SimpleXMLRPCServer.SimpleXMLRPCDispatcher.__init__(self, False, None)
        SocketServer.BaseServer.__init__(self, server_address, SecureDocXMLRpcRequestHandler)
        self.register_instance(registerInstance) # for some reason, have to register instance down here!

        # SSL socket stuff
        ctx = SSL.Context(SSL.SSLv23_METHOD)
        ctx.use_privatekey_file(keyFile)
        ctx.use_certificate_file(certFile)
        # verify
        ctx.load_verify_locations('cert/rpc-ca.crt')
        ctx.set_verify(SSL.VERIFY_PEER|SSL.VERIFY_FAIL_IF_NO_PEER_CERT, self._verify)
        self.socket = SSL.Connection(ctx, socket.socket(self.address_family, self.socket_type))
        self.server_bind()
        self.server_activate()

        # requests count and condition, to allow for keyboard quit via CTL-C
        self.requests = 0
        self.rCondition = Condition()
    def _verify(self, connection, x509, errnum, errdepth, ok):
        print '_verify (ok=%d):' % ok
        print '  subject:', x509.get_subject()
        print '  issuer:', x509.get_issuer()
        print '  errnum %s, errdepth %d' % (errnum, errdepth)
        return ok

    def startup(self):
        'run until quit signaled from keyboard...'
        print 'server starting; hit CTRL-C to quit...'
        while True:
            try:
                self.rCondition.acquire()
                start(self.handle_request, ()) # we do this async, because handle_request blocks!
                while not self.requests:
                    self.rCondition.wait(timeout=3.0)
                if self.requests: self.requests -= 1
                self.rCondition.release()
            except KeyboardInterrupt:
                print "quit signaled, i'm done."
                return

    def get_request(self):
        request, client_address = self.socket.accept()
        self.rCondition.acquire()
        self.requests += 1
        self.rCondition.notifyAll()
        self.rCondition.release()
        return (request, client_address)

    def listMethods(self):
        'return list of method names (strings)'
        methodNames = self.funcs.keys()
        methodNames.sort()
        return methodNames

    def methodHelp(self, methodName):
        'method help'
        if methodName in self.funcs:
            return self.funcs[methodName].__doc__
        else:
            raise Exception('method "%s" is not supported' % methodName)





curr_dir = os.getcwd()
logfile = os.path.join(curr_dir, 'daemon.log')
sslkey = os.path.join(curr_dir, 'host.key')
sslcrt = os.path.join(curr_dir, 'host.crt')
logging.basicConfig(filename=logfile, level=logging.DEBUG, 
        format="%(asctime)s [%(levelname)s] %(message)s")

def sig_hup_handler(signum, frame):
    logging.debug('Signal handler called with signal %s', signum)

signal.signal(signal.SIGHUP, sig_hup_handler)


def MainServer():
    """Main server with access to db"""
    class Rpc:
        '''Rpc interface'''
        title = 'rpc'
        name = 'rpc'
        def status1(self,a):
            '''Return status'''
            return 'ok ',a
        def flow_put(self,data):
            try:
                handle = open('ffile', 'w')
                handle.write(data.data)
                handle.close()
            except Exception,e:
                print e
                return False
            return True
            

    server_address = ('127.0.0.1', 9779) # (address, port)
    server = SecureDocXMLRPCServer(Rpc(), server_address, sslkey, sslcrt)    
    sa = server.socket.getsockname()
    print "Ok in https://%s:%d" % (sa[0], sa[1])
    server.startup()


if __name__ == '__main__':
    import getopt,sys
    daemon = False
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'D')
    except getopt.GetoptError, err:
        print str(err)
        sys.exit(2)
    for o,a in opts:
        if o == '-D':
            daemon = True
        else:
            assert False, 'unhandled option'

    if daemon:
        daemonize.daemonize(stderr=os.path.join(curr_dir, 'panic.log'))

    MainServer()

