import ConfigParser
import re
import time
import Logger
import shlex
import subprocess
from subprocess import Popen, PIPE
from threading import Timer


BASE_CMD = "ipmitool -I lanplus -H %s -U %s -P %s " # (node_ip, user, pwd)
REBOOT_NODE_CMD = "chassis power reset"
START_NODE_CMD = "chassis power on"
GET_WATCHDOG_CMD = "mc watchdog get"
GET_POWER_STATUS_CMD = "power status"
POWER_STATUS_SUCCESS_MSG = "Power is on"
REBOOT_NODE_SUCCESS_MSG = "Reset"
START_NODE_SUCCESS_MSG = "Up/On"
WATCHDOG_THRESHOLD = 4
WATCHDOG_INITIAL = "Initial Countdown"
WATCHDOG_PRESENT = "Present Countdown"

config = ConfigParser.RawConfigParser()
config.read("controllerHA.conf")

def reboot_node(node_name):
    if is_node_ipmi_supported(node_name):
        try:
            cmd = get_reboot_node_cmd(node_name)
            response = subprocess.check_output(cmd, shell=True)
            if REBOOT_NODE_SUCCESS_MSG in response:
                Logger.write("successful reboot node %s" % node_name)
                return True
        except Exception as e:
            Logger.write(str(e))
            return False
    else:
        return False

def start_node(node_name):
    if is_node_ipmi_supported(node_name):
        try:
            cmd = get_start_node_cmd(node_name)
            response = subprocess.check_output(cmd, shell=True)
            if START_NODE_SUCCESS_MSG in response:
                Logger.write("successful start node %s" % node_name)
                return True
        except Exception as e:
            Logger.write(str(e))
            return False
    else:
        return False

def get_watchdog_status(node_name):
    interval = (WATCHDOG_THRESHOLD / 2)
    prev_initial = None
    prev_present = None
    for _ in range(3):
        initial = get_watchdog_value(node_name, WATCHDOG_INITIAL)
        present = get_watchdog_value(node_name, WATCHDOG_PRESENT)
        if initial == False or present == False:
            return "Error"
        if (initial - present) > WATCHDOG_THRESHOLD:
            return "Error"
        if prev_initial != initial:
            prev_initial = initial
            prev_present = present
            time.sleep(float(interval))
            continue
        if (prev_present - present) < interval:
            return "OK"
        prev_present = present
        time.sleep(float(interval))
    return "Error"

def get_watchdog_value(node_name, value_type):
    cmd = get_watchdog_cmd(node_name)
    try:
        response = run(cmd, 1)
        if response == None:
            return False
        for info in response.split("\n"):
            if "Stopped" in info:
                return False
            if not info:
                break
            if value_type in info:
                return int(re.findall("[0-9]+", info)[0])
    except Exception as e:
        return False

def get_power_status(node_name):
    status = "OK"
    cmd = get_power_status_cmd(node_name)
    try:
        response = run(cmd,timeout_sec=1)
        if response == None:
            return False
        if POWER_STATUS_SUCCESS_MSG not in response:
            status = "Error"
    except Exception as e:
        Logger.write("IpmiModule getPowerStatus - The controller Node %s's IPMI session can not be established. %s" % (
                    node_name, e))
        status = "Error"
    finally:
        return status

    

def get_reboot_node_cmd(node_name):
    return get_base_cmd(node_name) + REBOOT_NODE_CMD

def get_start_node_cmd(node_name):
    return get_base_cmd(node_name) + START_NODE_CMD

def get_watchdog_cmd(node_name):
    return get_base_cmd(node_name) + GET_WATCHDOG_CMD

def get_power_status_cmd(node_name):
    return get_base_cmd(node_name) + GET_POWER_STATUS_CMD


def get_base_cmd(node_name):
    ip = config.get("ipmi", node_name)
    user = config.get("ipmi_user", node_name).split(",")[0]
    pwd = config.get("ipmi_user", node_name).split(",")[1]
    return BASE_CMD % (ip, user, pwd)

def is_node_ipmi_supported(node_name):
    return node_name in config._sections['ipmi']

def run(cmd, timeout_sec):
    proc = Popen(shlex.split(cmd), stdout=PIPE, stderr=PIPE)
    timer = Timer(timeout_sec, proc.kill)
    try:
        timer.start()
        stdout, stderr = proc.communicate()
    finally:
        timer.cancel()
        if stdout == "": return None
        return stdout

if __name__ == '__main__':
    print reboot_node("controller2")

