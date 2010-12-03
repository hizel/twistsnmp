#!/usr/bin/env python
# -*- coding: utf-8 -*-

from datetime import datetime
from time import time
from twisted.internet.task import LoopingCall
from twisted.internet import reactor, defer
from twisted.enterprise import adbapi
from twisted.web import xmlrpc, server, resource
from twisted.internet.protocol import Protocol, ClientCreator

from pysnmp.entity import engine, config
from pysnmp.carrier.twisted import dispatch
from pysnmp.carrier.twisted.dgram import udp
from pysnmp.entity.rfc3413 import cmdgen

from logging import basicConfig, DEBUG, debug, error, info

def _cbFun(sendRequestHandle, errorIndication,
        errorStatus, errorIndex, varBinds, cbCtx):
    cbCtx.callback((errorIndication, errorStatus, errorIndex, varBinds, cbCtx))

class GetCommandGenerator(cmdgen.GetCommandGenerator):
    def sendReq(
            self,
            snmpEngine,
            addrName,
            varBinds,
            contextEngineId=None,
            contextName=''
            ):
        df = defer.Deferred()
        cmdgen.GetCommandGenerator.sendReq(
                self,
                snmpEngine,
                addrName,
                varBinds,
                _cbFun,
                df,
                contextEngineId,
                contextName
                )
        return df
    def _handleResponse(
            self,
            snmpEngine,
            transportDomain,
            transportAddress,
            messageProcessingModel,
            securityModel,
            securityName,
            securityLevel,
            contextEngineId,
            contextName,
            pduVersion,
            PDU,
            timeout,
            retryCount,
            pMod,
            rspPDU,
            sendRequestHandle,
            (cbFun, cbCtx)
            ):
        cbCtx.callback(
                (None,
                    pMod.apiPDU.getErrorStatus(rspPDU),
                    pMod.apiPDU.getErrorIndex(rspPDU),
                    pMod.apiPDU.getVarBinds(rspPDU),
                    cbCtx)
                )

class CarbonProtocol(Protocol):
    def __init__(self, path, value, timestamp):
        self.path = path
        self.value = value
        self.timestamp = timestamp

    def sendMessage(self):
        debug('send %s %s %s' % (self.path, self.value, self.timestamp))
        self.transport.write('%s %s %s\n' % (self.path, self.value,
            self.timestamp))
        self.transport.loseConnection()

class TwistSnmp(object):
    def __init__(self, dbapiName, dbname, dbuser, dbpass='', dbhost='localhost'):
        debug('init')
        self.snmpEngine = engine.SnmpEngine()
        self.snmpEngine.registerTransportDispatcher(dispatch.TwistedDispatcher())
        config.addSocketTransport(self.snmpEngine, udp.domainName, udp.UdpTwistedTransport().openClientMode())

        try:
            self.dbpool = adbapi.ConnectionPool('MySQLdb', db=dbname, user=dbuser,
                    passwd=dbpass, host=dbhost, cp_noisy=True,
                    cp_reconnect=True)
        except ImportError:
            error('Could not import database library')
        except Exception, ex:
            error('Fail %s' % str(ex))

        self.hosts = ()
        self.jobs = ()
        self.snmp_jobs = {}

    def _job_afterconnect(self, p):
        p.sendMessage()
        debug('send message to carbon')

    def _snmp_recv_task(self, (errorIndication, errorStatus, errorIndex, varBinds, cbCtx)):
        debug('snmp recv for %s %s' % (cbCtx.job_host, cbCtx.job_uid))
        cbCtx.snmp_jobs[cbCtx.job_name][2] = int(time())
        if errorIndication or errorStatus:
            error('snmp error for job %s %s' % (cbCtx.job_name, cbCtx.job_uid))
            cbCtx.snmp_jobs[cbCtx.job_name][3] = 'ERROR'
            return
        cbCtx.snmp_jobs[cbCtx.job_name][1] = varBinds
        cbCtx.snmp_jobs[cbCtx.job_name][3] = 'OK'
        if cbCtx.snmp_jobs[cbCtx.job_name][4] != None:
            newvalue = int((varBinds[0][1]-cbCtx.snmp_jobs[cbCtx.job_name][4])/(int(time())-cbCtx.snmp_jobs[cbCtx.job_name][5]))
            c = ClientCreator(reactor, CarbonProtocol, *( cbCtx.job_name,
                newvalue, int(time())))
            c.connectTCP("localhost", 2003).addCallback(self._job_afterconnect)
        cbCtx.snmp_jobs[cbCtx.job_name][4] =  varBinds[0][1]
        cbCtx.snmp_jobs[cbCtx.job_name][5] =  int(time())

    def _job_snmp_task(self, host, name, uid_str):
        uid_tuple = uid_str.split('.')[1:]
        debug('generate snmp from %s %s %s' % (host, name, uid_str))
        uid = tuple(int(j) for j in uid_tuple)
        getCmdGen = GetCommandGenerator()
        df = getCmdGen.sendReq(
                self.snmpEngine,
                host,
                ((uid, None),),
                )
        df.job_host = host
        df.job_uid = uid
        df.job_name = name
        df.snmp_jobs = self.snmp_jobs 
        df.addCallback(self._snmp_recv_task)

    def _job_reschedule_task(self, new_jobs):
        set_new = set(new_jobs)
        set_old = set(self.jobs)
        if set_new ^ set_old:
            jobs_add = set_new - set_old
            jobs_rem = set_old - set_new
            for job in jobs_rem:
                job_name = '%s.%s' % (job[0],job[1])
                info('rem new jobs: %s ' % job_name)
                if job_name in self.snmp_jobs:
                    self.snmp_jobs[job_name][0].stop()
                    del self.snmp_jobs[job_name]
            for job in jobs_add:
                job_host = job[0]
                job_name = '%s.%s' % (job[0],job[1])
                job_freq = job[3]
                job_uid = job[2]
                info('add new jobs: %s with %d sec' % (job_name, job_freq))
                snmp_job = LoopingCall(self._job_snmp_task, *(job_host, job_name, job_uid))
                snmp_job.start(job_freq)
                self.snmp_jobs[job_name] = [snmp_job, 0, 0, 'UNKNOWN', None,
                        None]
            self.jobs = new_jobs
        
    def _db_receive_task(self, new_hosts):
        set_new = set(new_hosts)
        set_old = set(self.hosts)
        if set_new ^ set_old:
            # need update host_list 
            hosts_add = set_new - set_old
            hosts_rem = set_old - set_new
            for host in hosts_rem:
                name = host[5]
                config.delTargetAddr(self.snmpEngine, name)
                config.delTargetParams(self.snmpEngine, name)
                config.delV1System(self.snmpEngine, name)
                info('remove old host %s with community %s version %s' % host[:3])
            for host in hosts_add:
                community = host[1]
                version = host[2]
                name = host[4]
                host_addr = host[0]
                host_port = host[3]
                debug('add V1System name:%s community:%s',name, community)
                config.addV1System(self.snmpEngine, name, community,
                        transportTag=name)

                debug('addTargetParams name:%s version:%s',name, version)
                if version == 'v1':
                    config.addTargetParams(self.snmpEngine, name, name, 
                            'noAuthNoPriv', 0)
                else:
                    config.addTargetParams(self.snmpEngine, name,
                            name, 'noAuthNoPriv', 1)
                debug('addTargetAddr name:%s addr:%s:%d',name, host_addr, host_port)
                config.addTargetAddr(
                        self.snmpEngine, 
                        name,   
                        config.snmpUDPDomain,
                        (host_addr, host_port),
                        name,
                        tagList=name)
                debug('add new host %s with community %s version %s succesful' % host[:3])

            self.hosts = new_hosts
        deferred = self.dbpool.runQuery("""select hosts.name, host_job.name, uid,
                freq from host_job,hosts where hosts.id = host_job.host_id
                """)
        deferred.addCallback(self._job_reschedule_task)

    def _db_err_task(self, err):
        debug(err)

    def _db_task(self):
        df = self.dbpool.runQuery("""select host, rcommunity, version, port, name from
                hosts""")
        df.addCallback(self._db_receive_task)
        df.addErrback(self._db_err_task)

    def start(self):
        self.db_lc = LoopingCall(self._db_task)
        self.db_lc.start(15)

    def status(self):
        return self.snmp_jobs

    def stop(self):
        pass

class StatusWeb(resource.Resource):
    isLeaf = True
    def __init__(self, tw):
        resource.Resource.__init__(self)
        self.tw = tw
        debug('init simple')
    def render_GET(self, request):
        head =  '<html><title></title><body>'
        footer = '</body></html>'
        table = '<table>'
        status = self.tw.status()
        for job in status:
            table += '<tr>'
            table += '<td>'+job+'</td>'
            table += '<td>'+str(status[job][2])+'</td>'
            table += '<td>'+status[job][3]+'</td>'
            table += '</tr>'
        table += '</table>'
        return head+table+footer


basicConfig(level=DEBUG, format='%(asctime)s %(levelname)s %(message)s')

tw = TwistSnmp('MySQLdb', dbname='mon', dbuser='root')
tw.start()

reactor.listenTCP(8080, server.Site(StatusWeb(tw)))

reactor.run()

