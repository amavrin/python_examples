#!/usr/bin/python

from zabbix_api import ZabbixAPI
import sys
import datetime
import time
import argparse
import ConfigParser

def fetch_to_csv(username,password,server,hostname,key,output,datetime1,datetime2,debuglevel):

    zapi = ZabbixAPI(server=server, log_level=debuglevel)
    try:
        zapi.login(username, password)
    except:
        print "zabbix server is not reachable: %s" % (server)
        return False
    host = zapi.host.get({"filter":{"host":hostname}, "output":"extend"})
    if(len(host)==0):
        print "hostname: %s not found in zabbix server: %s, exit" % (hostname,server)
        return False
    else:
        hostid=host[0]["hostid"]
    if key:
        #print "key is: %s" %(key)
        itemid = zapi.item.get({"filter":{"key_":key, "hostid":hostid} , "output":"extend"})
        if(len(itemid)==0):
            print "item key: %s not found in hostname: %s" % (key,hostname)
            return False
        itemidNr=itemid[0]["itemid"]
        itemName=itemid[0]["name"]
        if (output == ''):
            output=hostname+".csv"
        f = open(output, 'a')
        str1=""

        d1=datetime.datetime.strptime(datetime1,'%Y-%m-%d %H:%M:%S')
        d2=datetime.datetime.strptime(datetime2,'%Y-%m-%d %H:%M:%S')
        timestamp1=time.mktime(d1.timetuple())
        timestamp2=time.mktime(d2.timetuple())
        history = zapi.history.get({"history":itemid[0]["value_type"],"time_from":timestamp1,"time_till":timestamp2, "itemids":[itemidNr,], "output":"extend" })
        inc=0
        for h in history:
            tstamp = h["clock"]
            strtime = time.strftime("%Y-%m-%d %H:%M:%S",  time.localtime( float(tstamp) ) )
            str1 = str1 + key + ";" + itemName + ";" + tstamp +";"+ strtime +";"+h["value"] + "\n"
            inc=inc+1
        print str(inc) +" records has been fetched and saved into: " + output
        f.write(str1.encode("utf-8"))
        f.close()
    else:
        print "key is not specified. hostname: %s not found in zabbix server: %s, exit" % (hostname,server)
        return False
    return True

parser = argparse.ArgumentParser(description='Fetch history from aggregator and save it into CSV file')
parser.add_argument('-t1', dest='datetime1', default='',
           help='begin date-time, use this pattern \'2011-11-08 14:49:43\'')
parser.add_argument('-t2', dest='datetime2', default='',
           help='end date-time, use this pattern \'2011-11-08 14:49:43\'')
parser.add_argument('-v', dest='debuglevel', default=0, type=int,
           help='log level, default 0')
parser.add_argument('-c', dest='conffile', default="",
           help='config file')
args = parser.parse_args()

config = ConfigParser.ConfigParser()
config.read(args.conffile)

username = config.get('general_config', 'username')
password = config.get('general_config', 'password')
hostlist = config.get('general_config', 'hostlist')

for confhost in hostlist.split():
    server_IP = config.get(confhost, 'zserver')
    hostname = config.get(confhost, 'hostname')
    keylist = config.get(confhost, 'keylist')
    output = config.get(confhost, 'output')
    
    f = open(output, 'w')
    UTF8mark = [0xEF, 0xBB, 0xBF]
    newFileByteArray = bytearray(UTF8mark)
    f.write(newFileByteArray)
    str1="#key;name;timestamp;localtime;value\n"
    f.write(str1)
    f.close()

    if keylist:
        for k in keylist.split():
            fetch_to_csv(username, password, "http://"+server_IP+"/zabbix", hostname, k, output, args.datetime1, args.datetime2, args.debuglevel)
    else:
        print "keylist is not specified for host host %s, exit" % (hostname)
        sys.exit()
