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
import asyncore
import Logger
import State
import paramiko
import Role
import datetime
import IPMIModule
from DetectServiceThread import DetectServiceThread
from Detector import Detector


log_level = logging.getLevelName("INFO")
log_file_name = "/home/localadmin/controllerHA/controllerHA.log"
dir = os.path.dirname(log_file_name)
if not os.path.exists(dir):
    os.makedirs(dir)
logging.basicConfig(filename=log_file_name, level=log_level, format="%(asctime)s [%(levelname)s] : %(message)s")


config = ConfigParser.RawConfigParser()
config.read("controllerHA.conf")

REMOTE_CONTROLLER_NAME = config.get("default","remote_controller_name")
REMOTE_CONTROLLER = json.loads(config.get("default","remote_controller")) # should modify here
BLOCKSTORAGE = json.loads(config.get("default","blockstorage"))
DEFAULT_PRIMARY = "controller1"
GET_DRBD_ROLE_CMD = "drbdadm role r0".split()
GET_MYSQL_STATUS_CMD = "service mysql status".split()
MYSQL_START_CMD = "service mysql restart".split()
PING_CMD = "timeout 0.2 ping -c 1 %s" 
SELF_ISOLATED = False
REMOTE_CONTROLLER_FAILED = False
HA_HEALTHY = "HA_HEALTHY"
START_SERVICE_CMD = "sudo /home/localadmin/bin/isc21_ha_manual.sh start".split()
STOP_SERVICE_CMD = "sudo /home/localadmin/bin/isc21_ha_manual.sh stop".split()
INTERVAL = int(config.get("default","polling_interval"))
HA_DISABLED = False
TRANSIENT_FAILURE_TIME_OUT = int(config.get("default","transient_timeout"))
WAIT_PRIMARY_STOP_TIME = int(config.get("default","wait_primary_stop_time"))

dst = DetectServiceThread()
dst.daemon = True
dst.start()

detector = Detector(REMOTE_CONTROLLER_NAME)

def handleFailure(detect_result):
	if HA_DISABLED:
		return
	if secondChance(detect_result) == HA_HEALTHY:
		Logger.write("second chance %s" % HA_HEALTHY)
		return
	# key: (REMOTE_CONTROLLER_FAILED, SELF_ISOLATED, ROLE)
	recovery_methods = {
	(True, False, Role.PRIMARY): doNothing,
	(False, True, Role.PRIMARY): stopService,
	(True, False, Role.BACKUP): startService,
	(False, True, Role.BACKUP): doNothing
}
	role = Role.get_role()
	recovery_methods[(REMOTE_CONTROLLER_FAILED, SELF_ISOLATED, role)]()

	host_recovery_methods ={
	(True, False, Role.PRIMARY): recover_host,
	(False, True, Role.PRIMARY): doNothing,
	(True, False, Role.BACKUP): recover_host,
	(False, True, Role.BACKUP): doNothing
	}

	host_recovery_methods[(REMOTE_CONTROLLER_FAILED, SELF_ISOLATED, role)](detect_result)

def startService():
	time.sleep(WAIT_PRIMARY_STOP_TIME)
	Logger.write("start service...")
	localExec(START_SERVICE_CMD)
	role = Role.get_role()
	if role == Role.PRIMARY:
		Logger.write("start service success, drbd role is %s" % (Role.get_role(),))
		return True
	Logger.write("start service fail, drbd role is %s" % (Role.get_role(),))

def stopService():
	time.sleep(6)
	Logger.write("stop service..")
	localExec(STOP_SERVICE_CMD)
	role = Role.get_role()
	if role == Role.BACKUP or Role.ALL_BACKUPS:
		Logger.write("stop service success, drbd role is %s" % (Role.get_role(),))
		return True
	Logger.write("stop service fail, drbd role is %s" % (Role.get_role(),))

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
	role = Role.get_role()
	mysqlStauts = getMysqlStatus()
	if not mysqlStauts and role == Role.PRIMARY:
		time.sleep(10)
		Logger.write("start mysql service")
		localExec(MYSQL_START_CMD)
		if getMysqlStatus():
			Logger.write("start mysql service success.")
		else:
			Logger.write("start mysql service fail")

def getMysqlStatus():
	try:
		res = localExec(GET_MYSQL_STATUS_CMD)
	except Exception as e:
		return False
	return True

def getHostName():
	return socket.gethostname()

def onlyBackup():
	if Role.get_role() == Role.ALL_BACKUPS:
		return True
	return False

def startFromOnlyBackup():
	global HA_DISABLED
	if HA_DISABLED:
		return
	if getHostName() == DEFAULT_PRIMARY:
		Logger.write("start from only backup..")
		startService()
		Logger.write("end start from only backup...") 

def secondChance(detect_result, time_out=TRANSIENT_FAILURE_TIME_OUT):
	if detect_result == State.NETWORK_FAIL:
		return network_second_chance(time_out)
	elif detect_result == State.SERVICE_FAIL:
		return service_second_chance()

def service_second_chance():
	status = None
	fail_services = detector.get_fail_services()
	if fail_services == None: return HA_HEALTHY
	client = paramiko.SSHClient()
	client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
	try:
		client.connect(REMOTE_CONTROLLER_NAME,username='root',timeout=5)
	except Exception as e:
		Logger.write("Excpeption : %s" % str(e))
		return False
	if "agents" in fail_services: # controllerHAd
		Logger.write("Start service failure recovery by restarting controllerHAd")
		cmd = "service ControllerHAd restart"
		try:
			client.exec_command(cmd)
			time.sleep(5)

			cmd = "ps aux | grep '[c]ontrollerHA.py'"
			stdin, stdout, stderr = client.exec_command(cmd)
			service = stdout.read()
			print service
			if "python controllerHA.py" in service:
				Logger.write("recover ControllerHAd success")
				status = HA_HEALTHY
			else:
				Logger.write("recover ControllerHAd fail")
			status = False
		except Exception as e:
			Logger.write("recover controllerHAd fail %s" % str(e))
			status = False
		finally:
			if status != HA_HEALTHY:
				client.exec_command("sudo /home/localadmin/bin/isc21_ha_manual.sh stop", timeout=30)
			client.close()
			return status
	else: # services
		check_timeout = 5
		service_mapping = {"libvirt": "libvirt-bin", "nova": "nova-compute", "qemukvm": "qemu-kvm"}
        fail_service_list = fail_services.split(":")[-1].split(";")[0:-1]
        try:
        	for fail_service in fail_service_list:
        		fail_service = service_mapping[fail_service]
        		cmd = "sudo service %s restart" % fail_service
        		client.exec_command(cmd)

        		while check_timeout > 0:
        			cmd = "service %s status" % fail_service
        			stdin, stdout, stderr = client.exec_command(cmd)  # check service active or not

        			if not stdout.read():
        				Logger.write("The controller %s service %s still doesn't work" % (REMOTE_CONTROLLER_NAME, fail_service))
        			else:
        				Logger.write("The controller %s service %s successfully restart" % (REMOTE_CONTROLLER_NAME, fail_service))
        				status = HA_HEALTHY
        				break
        			time.sleep(1)
        			check_timeout -= 1
        		status = False
        except Exception as e:
        	Logger.write(str(e))
        	status = False
        finally:
        	if status != HA_HEALTHY:
        		client.exec_command("sudo /home/localadmin/bin/isc21_ha_manual.sh stop", timeout=30)
        	client.close()
        	return status

def network_second_chance(time_out):
	Logger.write("start network second_chance...")
	Logger.write("wait %s seconds and check again" % time_out)
	time.sleep(time_out)
	if ping(REMOTE_CONTROLLER):
		Logger.write("The network status of %s return to health" % REMOTE_CONTROLLER_NAME)
		return HA_HEALTHY
	Logger.write("after sleep 30s, %s still network unreachable" % REMOTE_CONTROLLER_NAME)
	return False

def recover_host(detect_result):
	if detect_result == State.POWER_FAIL:
		recover_host_by_start()
		return
	recover_host_by_reboot()

def recover_host_by_start(check_timeout=300):
	Logger.write("recover %s by start" % REMOTE_CONTROLLER_NAME)
	res = IPMIModule.start_node(REMOTE_CONTROLLER_NAME)
	prev = datetime.datetime.now()
	if not res:
		Logger.write("%s dont have ipmi support, abort host recovery" % REMOTE_CONTROLLER_NAME)
		return
	Logger.write("waiting node to start")
	time.sleep(5)
	while check_timeout > 0:
		try:
			if detector.service() == State.HEALTH:
				end = datetime.datetime.now()
				Logger.write("host recovery time %s" % (end - prev))
				Logger.write("recover controller %s success" % REMOTE_CONTROLLER_NAME)
				return True
		except Exception as e:
			Logger.write(str(e))
		finally:
			time.sleep(1)
			check_timeout -= 1
	return False

def recover_host_by_reboot(check_timeout=300):
	Logger.write("recover %s by reboot" % REMOTE_CONTROLLER_NAME)
	res = IPMIModule.reboot_node(REMOTE_CONTROLLER_NAME)
	prev = datetime.datetime.now()
	if not res:
		Logger.write("%s dont have ipmi support, abort host recovery" % REMOTE_CONTROLLER_NAME)
		return
	Logger.write("waiting node to reboot")
	time.sleep(5)
	while check_timeout > 0:
		try:
			if detector.service() == State.HEALTH:
				end = datetime.datetime.now()
				Logger.write("host recovery time %s" % (end - prev)) 
				Logger.write("recover controller %s success" % REMOTE_CONTROLLER_NAME)
				return True
		except Exception as e:
			Logger.write(str(e))
		finally:
			time.sleep(1)
			check_timeout -= 1
	return False

def detect():
	global HA_DISABLED
	global SELF_ISOLATED
	global REMOTE_CONTROLLER_FAILED
	detect_result = detector.detect_result()
	if detect_result != State.HEALTH:
		if not ping(BLOCKSTORAGE):
			Logger.write("self") 
			SELF_ISOLATED = True
		else:
			Logger.write("remote")
			REMOTE_CONTROLLER_FAILED = True
		return detect_result
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
		detect_result = detect()
		Logger.write(detect_result) 
		if detect_result != HA_HEALTHY:
			Logger.write("detection time %s" % datetime.datetime.now())
			handleFailure(detect_result)
			HA_DISABLED = True
			Logger.write("HA_DISABLED %s" % HA_DISABLED)
		#checkMysql()
		time.sleep(INTERVAL)

if __name__ == '__main__':
	try:
		main()
	except Exception as e:
		Logger.write(str(e))