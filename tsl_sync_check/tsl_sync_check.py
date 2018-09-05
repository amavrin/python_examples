#!/usr/bin/python
# -*- coding: utf-8 -*-
import subprocess
import os
import re
import argparse
import ConfigParser
import logging
import sys
import xml.dom.minidom
import urllib2

Tsl_Data = ""


FORMAT = '%(asctime)-15s %(message)s'
logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=FORMAT)

def get_tsl_file(url, file):
    logging.debug('downloading TSL file from %s', url)
    global Tsl_Data
    Tsl_Data = urllib2.urlopen(url).read()
    if file != "":
        out = open(file, 'w')
        out.write(Tsl_Data)
        out.close()
        logging.info("saved TSL data in %s" % file)

def parse_tsl_file(keys_wo_certs):
    global Tsl_Data
    tsl_dom = xml.dom.minidom.parseString(Tsl_Data)

    Keys = tsl_dom.getElementsByTagName(u"Ключ")
    key_ids = []
    certs_key_nocert = []

    for key in Keys:
        ids = key.getElementsByTagName(u"ИдентификаторКлюча")
        kp = ids[0].firstChild.data
        logging.debug("found key with id %s" % kp)
        key_ids.append(kp)

        if kp in set(keys_wo_certs):
            logging.debug("%s reported has no valid certs" % kp)
            crts = key.getElementsByTagName(u"Отпечаток")
            for c in crts:
                cp = c.firstChild.data
                logging.debug("cert with id %s corresponds to key %s reported has no valid certs" % (cp, kp))
                certs_key_nocert.append(cp)

    Certs = tsl_dom.getElementsByTagName(u"ДанныеСертификата")
    cert_ids = []

    for cer in Certs:
        ids = cer.getElementsByTagName(u"Отпечаток")
        for id in ids:
            cp = id.firstChild.data
            logging.debug("found cert with id %s" % cp)
            cert_ids.append(cp)

    return key_ids, cert_ids, certs_key_nocert

def run_tsl_sync(exec_args = []):
    logging.debug('starting process: argument array: %s', exec_args)
    procout = ""
    proc = subprocess.Popen(exec_args, stdout=subprocess.PIPE)

    while proc.returncode is None:
        procout += proc.stdout.read()
        proc.poll()

    if proc.returncode != 0:
        logging.error(u"Программа синхронизации сертификатов завершилась с ошибкой, статус завершения %s, см. лог-файл" % proc.returncode)
        sys.exit(1)
    else:
        logging.debug("command exited with code %s" % proc.returncode)

    old_cert = re.compile('^.+Сертификат с отпечатком ([0-9A-F]{40}) является устаревшим и не будет загружен.*$', re.UNICODE)
    old_certs = []

    no_cert_key = re.compile('^.+Не найдено ни одного действительного сертификата для ключа с иденитификатором ([0-9A-F]{40})\..*$', re.UNICODE)
    no_cert_keys = []

    a = procout.splitlines()
    for logline in a:
        logging.debug("line: %s" % logline)
        old_cert_match = old_cert.match(logline)
        if old_cert_match:
            c = old_cert_match.group(1)
            logging.debug("old cert: %s" % c)
            old_certs.append(c)
        no_cert_key_match = no_cert_key.match(logline)
        if no_cert_key_match:
            k = no_cert_key_match.group(1)
            logging.debug("no-cert key: %s" % k)
            no_cert_keys.append(k)

    return no_cert_keys, old_certs

    return no_cert_keys

def cert_dnld_stat(dest_dir):
    sav_cert = os.popen("ls -1 %s/*.cer" % dest_dir).read().splitlines()
    dnld_crl = os.popen("ls -1 %s/*.crl" % dest_dir).read().splitlines()

    num_cert = len(sav_cert)
    num_crl = len(dnld_crl)

    print "saved .cer files: %s" % num_cert
    print "downloaded .crl files: %s" % num_crl

    sav_cert_ids = map(lambda x: os.path.basename(x).split('.')[0], sav_cert)
    dnld_crl_ids = map(lambda x: os.path.basename(x).split('.')[0], dnld_crl)

    for c in sav_cert_ids:
        logging.debug("cert id %s saved" % c)

    return sav_cert_ids

def diff3(l1, l2, l3):
    s2 = set(l2)
    s3 = set(l3)
    return [item for item in l1 if ( item not in s2 and item not in s3 ) ]


parser = argparse.ArgumentParser(description='Run TSL Sync utility and compare statistics')
parser.add_argument('-c', dest='conffile', default="/usr/local/etc/tsl_sync_check.ini", help='config file')
args = parser.parse_args()

logging.debug('starting with arguments %s', args)

config = ConfigParser.ConfigParser()
config.read(args.conffile)


prog_path = config.get('program', 'exec')
dest_dir = config.get('program', 'dest_dir')
clean_dest_dir = config.get('program', 'clean_dest_dir')
append_dir = config.get('program', 'append_dir')

tsl_url = config.get('tsl_list', 'url')
save_copy = config.get('tsl_list', 'save_copy')
save_filename = ""
if save_copy == "yes":
    save_filename = config.get('tsl_list', 'save_filename')

if clean_dest_dir == "yes":
    logging.debug("clean destination directory %s" % dest_dir)
    os.system("if [ ! -d %s ] ; then mkdir %s ; fi" % (dest_dir, dest_dir) )
    os.system("find %s -regextype egrep -regex '.*\/[A-F0-9]{40}.(cer|crl|txt)' -delete" % dest_dir)
    # control run: check if there any files remains
    out = os.popen("find " + dest_dir).read()
    logging.debug("files in destination directory:")
    logging.debug(out)

run_array = prog_path.split()

if append_dir == "yes":
    run_array.append(dest_dir)

tsl_keys = []
tsl_certs = []
certs_bykey_nocer = []
rep_keys = []
rep_certs = []
sav_certs = []
#dn_crl = []

logging.info("Скачиваем список доверенных УЦ")
get_tsl_file(tsl_url, save_filename)

logging.info("Запускаем утилиту синхронизации сертификатов")
rep_keys, rep_certs = run_tsl_sync(run_array)

logging.info("Обрабатываем сохранённые сертификаты")
sav_certs = cert_dnld_stat(dest_dir)

logging.info("Анализируем TSL-файл")
tsl_keys, tsl_certs, certs_bykey_nocer = parse_tsl_file(rep_keys)

all_outdated_certs = list(set(rep_certs) | set(certs_bykey_nocer))

diff_cert = diff3(tsl_certs, all_outdated_certs, sav_certs)
for c in diff_cert:
    logging.error(u"Ошибка: сертификат с иденитификатором %s в списке TSL, сертификат не сохранён, сообщения об ошибке не было" % c)

#logging.info(u"%s идентификаторов ключей в списке TSL" % len(tsl_keys))
str = u'%s идентификаторов сертификатов в списке TSL' % len(tsl_certs)
print str.encode("utf-8")
str = u'%s сертификатов просрочено' % len(all_outdated_certs)
print str.encode("utf-8")
str = u'%s сертификатов сохранено' % len(sav_certs)
print str.encode("utf-8")
str = u'Расхождение: %s сертификатов' % len(diff_cert)
print str.encode("utf-8")
