#!/usr/bin/python

import os
import sys
import paramiko
import tempfile
import argparse
import errno
from pwd import getpwnam, getpwuid
import ConfigParser
import httplib
import base64
import json

def call_update_api(host, port, user, password):
    h = httplib.HTTPConnection("%s:%s" % (host, port) )
    userAndPass = base64.b64encode(b"%s:%s" % (user, password) ).decode("ascii")
    headers = { 'Authorization' : 'Basic %s' %  userAndPass }
    try:
        h.request('GET', '/sx/api/rest/csrf-token', headers=headers)
        r = h.getresponse()
        data=r.read()
        d = json.loads(data)
        headers[d['headerName']] = d['token']
        c=r.getheader('set-cookie')
        headers['Cookie']=c
        h.request('PUT', '/sx/api/rest/security/certificates', headers=headers)
    except:
        print "can not call update API on %s" % (host)

def setup_local():
    try:
        os.mkdir(spool_dir)
    except OSError as e:
        if (e.errno != errno.EEXIST):
            print "can not make local spool: %s" % (spool_dir)
            sys.exit(1)

    tmp_dir = tempfile.mkdtemp(dir=spool_dir)
    return tmp_dir

def remote_cmd(client, cmd):
    channel = client.get_transport().open_session()
    channel.get_pty()
    channel.exec_command(cmd)

    output = ""

    while channel.exit_status_ready() == False:
        output += channel.recv(1024)

    status = channel.recv_exit_status()

    return status, output

def download(host, download_cmd, dir):
    keyfile = getpwuid(os.geteuid()).pw_dir + "/.ssh/id_rsa"
    k = paramiko.RSAKey.from_private_key_file(keyfile)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(host, username="root", pkey = k)
    except:
        print "can not connect to %s" % (host)
        return

    cmd = "mktemp -d -p " + dir
    s, output = remote_cmd(client, cmd)
    if s:
        print "command %s on %s says %s (exit code %s)" % (host, cmd, output, s)
        sys.exit(1)

    remote_tmp_dir = output.rstrip()

    cmd = download_cmd + " " + remote_tmp_dir
    s, output = remote_cmd(client, cmd)
    if s:
        print "command %s on %s says %s (exit code %s)" % (host, cmd, output, s)
        sys.exit(1)


    cmd = "rsync -a -e ssh root@%s:%s ." % (host, remote_tmp_dir)
    e = os.system(cmd)
    if e:
        print "command %s returned %s" % (cmd, e)
        sys.exit(1)

    return os.path.basename(remote_tmp_dir)

    client.close()

def upload(local_dir, host, remote_dir):
    cmd = "rsync -a -e ssh %s/* root@%s:%s" % (local_dir, host, remote_dir)
    try:
        e = os.system(cmd)
    except:
        print "command %s failed" % (cmd)

def clean(session_dir):
    if os.geteuid() == 0:
        print "uid 0, not clearing session dir %s" % (session_dir)
        return
    print "clearing session dir %s" % (session_dir)
    os.system("rm -rf " + session_dir)

################################################

parser = argparse.ArgumentParser(description='Sync certs and CRLs')
parser.add_argument('-c', dest='conffile', default="/usr/local/etc/cert_sync.ini", help='config file')
parser.add_argument('-v', action='store_true', dest='verbose')
args = parser.parse_args()

config = ConfigParser.ConfigParser()
config.read(args.conffile)

local_user = config.get('local', 'user')
spool_dir = config.get('local', 'spool_dir')
source_host = config.get('source', 'host')
target_hosts = config.get('target', 'hosts')
source_download_dir_prefix = config.get('source', 'download_dir_prefix')
source_download_cmd = config.get('source', 'download_cmd')

os.seteuid(getpwnam(local_user).pw_uid)
session_dir = setup_local()
os.chdir(session_dir)

if args.verbose:
    print "downloading certificates"

transit_dir = download(source_host, source_download_cmd, source_download_dir_prefix)

if args.verbose:
    print "uploading certificates"

for thost in target_hosts.split():
    host = thost.split(":")[0]
    dir = thost.split(":")[1]
    port = config.get('api:%s' % host, 'port')
    user = config.get('api:%s' % host, 'user')
    password = config.get('api:%s' % host, 'password')
    upload(transit_dir, host, dir)
    call_update_api(host, port, user, password)

if args.verbose:
    print "cleaning"

clean(session_dir)

sys.exit(0)
