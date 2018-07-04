import subprocess

GET_DRBD_ROLE_CMD = "drbdadm role r0".split()
PRIMARY = ("Primary/Secondary","Primary/Unknown")
BACKUP = ("Secondary/Primary","Secondary/Unknown")
ALL_BACKUPS = ("Secondary/Secondary",)

def get_role():
	res = localExec(GET_DRBD_ROLE_CMD)
	if any(role in res for role in ALL_BACKUPS):
		return ALL_BACKUPS
	elif any(role in res for role in PRIMARY):
		return PRIMARY
	elif any(role in res for role in BACKUP):
		return BACKUP
	else:
		return None

def localExec(cmd):
	return subprocess.check_output(cmd, universal_newlines=True, stderr=subprocess.STDOUT)