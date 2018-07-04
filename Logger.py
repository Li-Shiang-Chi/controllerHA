import logging
import time

def write(message):
	time_stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
	logging.info("%s" % str(message))
