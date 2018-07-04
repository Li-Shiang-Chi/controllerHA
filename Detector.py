import IPMIModule
import Logger
import ConfigParser
import subprocess
import State
import socket
import time
import Role


config = ConfigParser.RawConfigParser()
config.read('controllerHA.conf')

class Detector():

    def __init__(self, controller):
        self.controller = controller
        self.ipmi_enable = IPMIModule.is_node_ipmi_supported(controller)
        self.sock = None
        self.port = int(config.get("detect","port"))
        self.function_map = [self.power, self.os, self.network, self.service]
        self.fail_map = [State.POWER_FAIL, State.OS_FAIL, State.NETWORK_FAIL, State.SERVICE_FAIL]
        self.check_service = True
        self.connect()

    def detect_result(self):
        role = Role.get_role()
        if role == Role.PRIMARY:
            highest_level_check = self.function_map[-2] # network
        elif role == Role.BACKUP:
            highest_level_check = self.function_map[-1] # service
        if highest_level_check() != State.HEALTH:
            state = self.verify(highest_level_check)
            if state == State.HEALTH:
                return Stae.HEALTH
            else:
                return state
        return State.HEALTH

    def verify(self, func):
        index = self.function_map.index(func)
        cloned_function_map = self.function_map[:]  # clone from function map
        cloned_function_map = cloned_function_map[0:index]  # remove uneeded detection function
        reversed_function_map = self.reverse(cloned_function_map)

        print reversed_function_map

        fail = self.fail_map[index]
        for _ in reversed_function_map:
            state = _()
            print state
            if state == State.HEALTH and _ == func:
                return State.HEALTH
            elif state == State.HEALTH:
                return fail
            elif not state == State.HEALTH:
                fail = state
        return fail

    def reverse(self, list):
        list.reverse()
        return list

    def connect(self):
        try:
            print "[" + self.controller + "] create socket connection"
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setblocking(0)
            self.sock.settimeout(1)
            self.sock.connect((self.controller, self.port))
        except Exception as e:
            Logger.write("detector connect error %s" % str(e))
            Logger.write("Init [" + self.controller + "] connection failed")

    def service(self):
        try:
            line = "polling request"
            self.sock.sendall(line)
            data, addr = self.sock.recvfrom(1024)
            if data == "OK":
                return State.HEALTH
            elif "error" in data:
                print data
                print "[" + self.controller + "]service Failed"
            elif not data:
                print "[" + self.controller + "]no ACK"
            else:
                print "[" + self.controller + "]Receive:" + data
            return State.SERVICE_FAIL
        except Exception as e:
            Logger.write(str(e))
            print "[" + self.controller + "] connection failed"
            self.connect()
            return State.SERVICE_FAIL

    def get_fail_services(self):
        try:
            line = "polling request"
            self.sock.sendall(line)
            data, addr = self.sock.recvfrom(1024)
            if data != "OK":
                return data
        except Exception as e:
            return "agents"
        

    def network(self):
        heartbeat_time = int(config.get("default","heartbeat_time"))
        network_fail_time = 0
        fail = False
        while heartbeat_time > 0:
            try:
                response = subprocess.check_output(['timeout', '0.2', 'ping', '-c', '1', self.controller],
                                                   stderr=subprocess.STDOUT, universal_newlines=True)
            except Exception as e:
                Logger.write("network transient failure")
                network_fail_time += 1
                pass
            finally:
                time.sleep(1)
                heartbeat_time -= 1
        heartbeat_time = int(config.get("default","heartbeat_time"))
        if network_fail_time == heartbeat_time:
            return State.NETWORK_FAIL
        return State.HEALTH

    def os(self):
        if not self.ipmi_enable:
            return State.HEALTH
        try:
            status = IPMIModule.get_watchdog_status(self.controller)
        except Exception as e:
            print str(e)
        if status == "OK":
            return State.HEALTH
        return State.OS_FAIL

    def power(self):
        if not self.ipmi_enable:
            return State.HEALTH
        try:
            status = IPMIModule.get_power_status(self.controller)
        except Exception as e:
            Logger.write("power detect %s" % str(e))
        if status == "OK":
            return State.HEALTH
        return State.POWER_FAIL

if __name__ == '__main__':
    detector = Detector("controller2")
    print detector.detect_result()