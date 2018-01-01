import controllerHA
import sys

def unittest_drbd_role(role):
	if role == "primary":
		if controllerHA.DRBD_role() == controllerHA.ROLE_PRIMARY:
			return True
		return False
	elif role == "backup":
		if controllerHA.DRBD_role() == controllerHA.ROLE_SECONDARY:
			return True
		return False

if __name__ == '__main__':
	if len(sys.argv) < 2:
		print "please input the role of the node, primary/backup"
		sys.exit(1)
	role = sys.argv[1]
	print unittest_drbd_role(role)
