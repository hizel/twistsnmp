#!/usr/bin/env python
# -*- coding: utf-8 -*-

from datetime import datetime
from twisted.internet.task import LoopingCall
from twisted.internet import reactor, defer
from twisted.enterprise import adbapi

from pysnmp.entity import engine, config
from pysnmp.carrier.twisted import dispatch
from pysnmp.carrier.twisted.dgram import udp
from pysnmp.entity.rfc3413 import cmdgen

from logging import basicConfig, DEBUG, debug, error, info

class GetCommandGenerator(cmdgen.GetCommandGenerator):
    def sendReq(
            self,
            snmpEngine,
            addrName,
            varBinds,
            cbFunc,
            contextEngineId=None,
            contextName=''
            ):
        df = defer.Deferred()
        cmdgen.GetCommandGenerator.sendReq(
                self,
                snmpEngine,
                addrName,
                varBinds,
                cbFunc,
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


snmpEngine = engine.SnmpEngine()
snmpEngine.registerTransportDispatcher(dispatch.TwistedDispatcher())
config.addSocketTransport(snmpEngine, udp.domainName,
        udp.UdpTwistedTransport().openClientMode())


dbpool = adbapi.ConnectionPool('MySQLdb', db='mon', user='root')
hosts = ()
jobs = ()
snmp_jobs = {}

def error_cb(sendRequestHandle, errorIndication, errorStatus, errorIndex,
                  varBinds, cbCtx):
    cbCtx.callback((errorIndication, errorStatus, errorIndex, varBinds, cbCtx))

def snmp_recv_task((errorIndication, errorStatus, errorIndex, varBinds, cbCtx)):
    debug('snmp recv for %s %s' % (cbCtx.job_host, cbCtx.job_uid))
    if errorIndication or errorStatus:
        error('snmp error for job %s %s' % (cbCtx.job_name, cbCtx.job_uid))
        return
    for oid, val in varBinds:
        if val is None:
            info('%s: %s' % (cbCtx.job_name, oid.prettyPrint()))
        else:
            info('%s: %s=%s' % (cbCtx.job_name, oid.prettyPrint(),
                val.prettyPrint()))


def job_snmp_task(host, name, uid_str):
    uid_tuple = uid_str.split('.')[1:]
    debug('generate snmp from %s %s %s' % (host, name, uid_str))
    uid = tuple(int(j) for j in uid_tuple)
    getCmdGen = GetCommandGenerator()
    df = getCmdGen.sendReq(
            snmpEngine,
            host,
            ((uid, None),),
            error_cb
            )
    df.job_host = host
    df.job_uid = uid
    df.job_name = name
    df.addCallback(snmp_recv_task)

def job_reschedule_task(new_jobs):
    global jobs
    global snmp_jobs
    set_new = set(new_jobs)
    set_old = set(jobs)
    if set_new ^ set_old:
        jobs_add = set_new - set_old
        jobs_rem = set_old - set_new
        for job in jobs_rem:
            job_name = '%s.%s' % (job[0],job[1])
            info('rem new jobs: %s ' % job_name)
            if job_name in snmp_jobs:
                snmp_jobs[job_name].stop()
        for job in jobs_add:
            job_host = job[0]
            job_name = '%s.%s' % (job[0],job[1])
            job_freq = job[3]
            job_uid = job[2]
            info('add new jobs: %s with %d sec' % (job_name, job_freq))
            snmp_job = LoopingCall(job_snmp_task, *(job_host, job_name, job_uid))
            snmp_job.start(job_freq)
            snmp_jobs[job_name] =  snmp_job
        jobs = new_jobs
        


def db_receive_task(new_hosts):
    global hosts
    set_new = set(new_hosts)
    set_old = set(hosts)
    if set_new ^ set_old:
        # need update host_list 
        hosts_add = set_new - set_old
        hosts_rem = set_old - set_new
        for host in hosts_rem:
            name = host[5]
            config.delTargetAddr(snmpEngine, name)
            config.delTargetParams(snmpEngine, name)
            config.delV1System(snmpEngine, name)
            info('remove old host %s with community %s version %s' % host[:3])
        for host in hosts_add:
            community = host[1]
            version = host[2]
            name = host[4]
            host_addr = host[0]
            host_port = host[3]
            debug('add V1System name:%s community:%s',name, community)
            config.addV1System(snmpEngine, name, community)

            debug('addTargetParams name:%s version:%s',name, version)
            if version == 'v1':
                config.addTargetParams(snmpEngine, name, name, 
                        'noAuthNoPriv', 0)
            else:
                config.addTargetParams(snmpEngine, name,
                        name, 'noAuthNoPriv', 1)
            debug('addTargetAddr name:%s addr:%s:%d',name, host_addr, host_port)
            config.addTargetAddr(
                    snmpEngine, 
                    name,   
                    config.snmpUDPDomain,
                    (host_addr, host_port),
                    name)
            debug('add new host %s with community %s version %s succesful' % host[:3])

        hosts = new_hosts
    deferred = dbpool.runQuery("""select hosts.name, host_job.name, uid,
            freq from host_job,hosts where hosts.id = host_job.host_id
            """)
    deferred.addCallback(job_reschedule_task)

def db_task():
    deferred = dbpool.runQuery('select host, rcommunity, version, port, name from hosts')
    deferred.addCallback(db_receive_task)
    debug('ran db_task')

basicConfig(level=DEBUG, format='%(asctime)s %(levelname)s %(message)s')

db_lc = LoopingCall(db_task)
db_lc.start(15)

reactor.run()

