#########################################################
#:Date: 2017/12/13
#:Version: 1
#:Authors:
#    - LSC <sclee@g.ncu.edu.tw>
#:Python_Version: 2.7
#:Platform: Unix
#:Description:
#	controllerHA service, deploy on both controller machines.
#	automatically change primary/backup when controller fails.
##########################################################

import subprocess
import os
import time
import sys
import socket
import ConfigParser
import json
import logging


log_level = logging.getLevelName("INFO")
log_file_name = "/home/localadmin/controllerHA/controllerHA.log"
dir = os.path.dirname(log_file_name)
if not os.path.exists(dir):
    os.makedirs(dir)
logging.basicConfig(filename=log_file_name, level=log_level, format="%(asctime)s [%(levelname)s] : %(message)s")


config = ConfigParser.RawConfigParser()
config.read("controllerHA.conf")

REMOTE_CONTROLLER = json.loads(config.get("default","remote_controller")) # should modify here
BLOCKSTORAGE = json.loads(config.get("default","blockstorage"))
DEFAULT_PRIMARY = "controller1"
GET_DRBD_ROLE_CMD = "drbdadm role r0".split()
GET_MYSQL_STATUS_CMD = "service mysql status".split()
MYSQL_START_CMD = "service mysql restart".split()
PING_CMD = "timeout 0.2 ping -c 1 %s" 
ROLE_PRIMARY = ("Primary/Secondary","Primary/Unknown")
ROLE_BACKUP = ("Secondary/Primary","Secondary/Unknown")
ROLE_ALL_BACKUPS = ("Secondary/Secondary",)
SELF_ISOLATED = False
REMOTE_CONTROLLER_FAILED = False
HA_HEALTHY = "HA_HEALTHY"
START_SERVICE_CMD = "sudo /home/localadmin/bin/isc21_ha_manual.sh start".split()
STOP_SERVICE_CMD = "sudo /home/localadmin/bin/isc21_ha_manual.sh stop".split()
INTERVAL = int(config.get("default","polling_interval"))
HA_DISABLED = False
TRANSIENT_FAILURE_TIME_OUT = int(config.get("default","transient_timeout"))
WAIT_PRIMARY_STOP_TIME = int(config.get("default","wait_primary_stop_time"))

def logMessage(message):
	time_stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
	logging.info("%s" % str(message))

def handleFailure():
	if HA_DISABLED:
		return
	if secondChance() == HA_HEALTHY:
		logMessage("second chance %s" % HA_HEALTHY)
		return
	# key: (REMOTE_CONTROLLER_FAILED, SELF_ISOLATED, ROLE)
	recovery_methods = {
	(True, False, ROLE_PRIMARY): doNothing,
	(False, True, ROLE_PRIMARY): stopService,
	(True, False, ROLE_BACKUP): startService,
	(False, True, ROLE_BACKUP): doNothing
}
	role = getDRBDRole()
	recovery_methods[(REMOTE_CONTROLLER_FAILED, SELF_ISOLATED, role)]()

def startService():
	time.sleep(WAIT_PRIMARY_STOP_TIME)
	logMessage("start service...")
	localExec(START_SERVICE_CMD)
	role = getDRBDRole()
	if role == ROLE_PRIMARY:
		logMessage("start service success, drbd role is %s" % (getDRBDRole(),))
		return True
	logMessage("start service fail, drbd role is %s" % (getDRBDRole(),))

def stopService():
	time.sleep(6)
	localExec(STOP_SERVICE_CMD)
	role = getDRBDRole()
	if role == ROLE_BACKUP or ROLE_ALL_BACKUPS:
		logMessage("stop service success, drbd role is %s" % (getDRBDRole(),))
		return True
	logMessage("stop service fail, drbd role is %s" % (getDRBDRole(),))

def doNothing():
	pass

def ping(ip_list):
	try:
		for ip in ip_list:
			cmd = (PING_CMD % ip).split()
			localExec(cmd)
		return True
	except Exception as e:
		return False

def checkMysql():
	role = getDRBDRole()
	mysqlStauts = getMysqlStatus()
	if not mysqlStauts and role == ROLE_PRIMARY:
		time.sleep(10)
		logMessage("start mysql service")
		localExec(MYSQL_START_CMD)
		if getMysqlStatus():
			logMessage("start mysql service success.")
		else:
			logMessage("start mysql service fail")

def getMysqlStatus():
	try:
		res = localExec(GET_MYSQL_STATUS_CMD)
	except Exception as e:
		return False
	return True

def getDRBDRole():
	res = localExec(GET_DRBD_ROLE_CMD)
	if any(role in res for role in ROLE_ALL_BACKUPS):
		return ROLE_ALL_BACKUPS
	elif any(role in res for role in ROLE_PRIMARY):
		return ROLE_PRIMARY
	elif any(role in res for role in ROLE_BACKUP):
		return ROLE_BACKUP
	else:
		return None
def getHostName():
	return socket.gethostname()

def onlyBackup():
	if getDRBDRole() == ROLE_ALL_BACKUPS:
		return True
	return False

def startFromOnlyBackup():
	global HA_DISABLED
	if HA_DISABLED:
		return
	if getHostName() == DEFAULT_PRIMARY:
		logMessage("start from only backup..")
		startService()
		logMessage("end start from only backup...") 

def secondChance(time_out=TRANSIENT_FAILURE_TIME_OUT):
	while time_out > 0:
		detection_result = detect()
		if detection_result == HA_HEALTHY:
			return HA_HEALTHY
		time_out-=1
		time.sleep(1)
	return False

def detect():
	global HA_DISABLED
	global SELF_ISOLATED
	global REMOTE_CONTROLLER_FAILED
	if not ping(REMOTE_CONTROLLER):
		if not ping(BLOCKSTORAGE):
			logMessage("self") 
			SELF_ISOLATED = True
			return
		else:
			logMessage("remote")
			REMOTE_CONTROLLER_FAILED = True
			return
	SELF_ISOLATED = False
	REMOTE_CONTROLLER_FAILED = False
	HA_DISABLED = False
	return HA_HEALTHY

def localExec(cmd):
	return subprocess.check_output(cmd, universal_newlines=True, stderr=subprocess.STDOUT)

def main():
	global HA_DISABLED
	while True:
		if onlyBackup() and not HA_DISABLED:
			startFromOnlyBackup()
			continue
		detection_result = detect()
		logMessage(detection_result) 
		if detection_result != HA_HEALTHY:
			handleFailure()
			HA_DISABLED = True
			logMessage("HA_DISABLED %s" % HA_DISABLED)
		checkMysql()
		time.sleep(INTERVAL)

if __name__ == '__main__':
	main()