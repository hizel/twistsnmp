#!/usr/bin/env python
# -*- coding: utf-8 -*-

from datetime import datetime
from twisted.internet.task import LoopingCall
from twisted.internet import reactor, defer
from twisted.enterprise import adbapi

from pysnmp.entity import engine, config
from pysnmp.carrier.twisted import dispatch
from pysnmp.carrier.twisted.dgram import udp
from pysnmp.entity.rfc3413.twisted import cmdgen

snmpEngine = engine.SnmpEngine()
snmpEngine.registerTransportDispatcher(dispatch.TwistedDispatcher())
config.addSocketTransport(snmpEngine, udp.domainName,
        udp.UdpTwistedTransport().openClientMode())


dbpool = adbapi.ConnectionPool('MySQLdb', db='mon', user='root')
hosts = ()
jobs = {}

def job_receive_task(new_jobs_q):
    print new_jobs_q
    if new_jobs_q:
        new_jobs = [ j[1:] for j in new_jobs_q ]
        if new_jobs_q[0] not in jobs:
            jobs[new_jobs_q[0]] = new_jobs

        print new_jobs


def db_receive_task(new_hosts):
    global hosts
    set_new = set(new_hosts)
    set_old = set(hosts)
    if set_new ^ set_old:
        # need update host_list 
        hosts_add = set_new - set_old
        hosts_rem = set_old - set_new
        for host in hosts_rem:
            config.delTargetAddr(snmpEngine, host[0])
            config.delTargetParams(snmpEngine, host[0])
            config.delV1System(snmpEngine, host[0])
            print 'remove old host %s with community %s version %s' % host[:3]
        for host in hosts_add:
            config.addV1System(snmpEngine, host[0], host[0])
            if host[2] == 'v1':
                config.addTargetParams(snmpEngine, host[0],
                        host[0], 'noAuthNoPriv', 0)
            else:
                config.addTargetParams(snmpEngine, host[0],
                        host[0], 'noAuthNoPriv', 1)
            config.addTargetAddr(
                    snmpEngine, 
                    host[0],   
                    config.snmpUDPDomain,
                    (host[0], host[3]),
                    host[0])
            deferred = dbpool.runQuery("""select hosts.host, hosts.alias, host_job.name, uid, i,
                    freq from host_job,hosts where hosts.id = host_job.host_id
                    and host_id=%s""" % host[4])
            deferred.addCallback(job_receive_task)
            print 'add new host %s with community %s version %s ' % host[:3]

        hosts = new_hosts

def db_task():
    deferred = dbpool.runQuery('select host, rcommunity, version, port, id from hosts')
    deferred.addCallback(db_receive_task)
    print datetime.now()


db_lc = LoopingCall(db_task)
db_lc.start(15)

reactor.run()

