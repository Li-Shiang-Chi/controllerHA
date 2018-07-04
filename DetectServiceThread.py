import asyncore
import socket
import ConfigParser
import subprocess
import libvirt
import threading
import Logger
import Role

POLLING_MESSAGE = "polling request"
SERVICE_HEALTH = "OK"
SERVICE_ERROR = "error:"


class DetectServiceThread(threading.Thread):

    def __init__(self):
        threading.Thread.__init__(self)
        config = ConfigParser.RawConfigParser()
        config.read('controllerHA.conf')

        self.port = int(config.get("detect", "port"))
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(('',self.port))
        self.libvirt_uri = "qemu:///system"

        print "detect service port", self.port

    def run(self):
        while True:
            data, addr = self.socket.recvfrom(2048)
            if POLLING_MESSAGE in data:
                if Role.get_role() == Role.BACKUP:
                    self.socket.sendto(SERVICE_HEALTH, addr)
                    continue
                res = self.check_services()
                if res == "":
                    self.socket.sendto(SERVICE_HEALTH, addr)
                else:
                    res = SERVICE_ERROR + res
                    self.socket.sendto(res, addr)

    def check_services(self):
        res = ""
        # check libvirt
        if not self._check_libvirt():
            res = "libvirt;"
        # check nova-compute
        if not self._check_nova_compute():
            res += "nova;"
        if not self._check_qemu_kvm():
            res += "qemukvm;"
        return res

    def _check_libvirt(self):
        try:
            conn = libvirt.open(self.libvirt_uri)
            if not conn:
                return False
        except Exception as e:
            print str(e)
            return False
        return True

    def _check_nova_compute(self):
        try:
            output = subprocess.check_output(['ps','-A'])
            if "nova-api" not in output:
                return False
        except Exception as e:
            return False
        return True

    def _check_qemu_kvm(self):
        try:
            output = subprocess.check_output(['service', 'qemu-kvm', 'status'])
            if "start/running" not in output:

                return False
        except Exception as e:
            print str(e)
            return False
        return True