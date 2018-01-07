#!/bin/bash
#check root privilege, only root can run this script.
if [ $EUID -ne 0 ] ; then
   echo "This script must be run as root" 1>&2
   set -e
fi

LOG_FILE=/home/localadmin/controllerHA/controllerHA_install.log
if [ ! -e "$LOG_FILE" ] ; then
    touch $LOG_FILE
fi

install_script_start() {
    DATE=`date`
    echo "==========$DATE controllerHA_install script start=============" >> $LOG_FILE
    install_dialog
}

install_dialog() {
    apt-get install dialog -y >> $LOG_FILE 2>> $LOG_FILE
    result=$?
    if [[ $result -eq 0 ]] ; 
    then
        echo "======dialog install success======" >> $LOG_FILE
    else
	echo "======dialog install failed======" >> $LOG_FILE
	set -e
    fi
    check_install
}

check_install() {
    dialog --title "automatically controller HA based on III environment installer" --yesno "Do you want to install controllerHA ?" 8 50
    result=$?
    if [ $result -eq 1 ] ; then
	clear;
	exit 1;
    elif [ $result -eq 255 ] ; then
	clear;
	exit 255;
    fi
    echo "check install end" >> $LOG_FILE
    remote_controller_ip_setup
}
remote_controller_ip_setup() {
    TMP_OUTPUT=/tmp/output.txt
    dialog --nocancel --inputbox "Enter remote controller ip. (if has mutiple ips, please seperate by ',':" 8 40  "192.168.3.13,192.168.4.13" 2>$TMP_OUTPUT
    remote_controller_ip=$(<$TMP_OUTPUT)
    rm $TMP_OUTPUT
    echo "remote controller_ip_setup end" >> $LOG_FILE
    blockstorage_ip_setup
}
blockstorage_ip_setup() {
    TMP_OUTPUT=/tmp/output.txt
    dialog --nocancel --inputbox "Enter blockstorage ip. (if has mutiple ips, please seperate by ',':" 8 40  "192.168.3.30,192.168.4.30" 2>$TMP_OUTPUT
    blockstorage_ip=$(<$TMP_OUTPUT)
    rm $TMP_OUTPUT
    echo "blockstorage_ip_setup end" >> $LOG_FILE
    default_controller_setup
}
default_controller_setup() {
    TMP_OUTPUT=/tmp/output.txt
    dialog --nocancel --inputbox "Enter default controller(ex: controller1):" 8 40  "controller1" 2>$TMP_OUTPUT
    default_controller=$(<$TMP_OUTPUT)
    rm $TMP_OUTPUT
    echo "default_controller_setup end" >> $LOG_FILE
    make_config_file
}

make_config_file() {
    CONFIG_FILE=/home/localadmin/controllerHA/controllerHA.conf
    rm $CONFIG_FILE
    touch $CONFIG_FILE
    echo "[default]" >> $CONFIG_FILE
    
    #controller ip string formating
    IFS=',' read -a array <<< "$remote_controller_ip"
    array_size=${#array[@]}
    unset controller_ip
    for ((i=0;i<array_size-1;i++))
    do
	controller_ip=\"$controller_ip${array[$i]}\",	
    done
    controller_ip=$controller_ip\"${array[$array_size-1]}\"
    echo "remote_controller = [$controller_ip]" >> $CONFIG_FILE
    
    #blockstorage ip string formating
    IFS=',' read -a array <<< "$blockstorage_ip"
    array_size=${#array[@]}
    unset blockstorage_ip
    for ((i=0;i<array_size-1;i++))
    do
        blockstorage_ip=\"$blockstorage_ip${array[$i]}\",
    done
    blockstorage_ip=$blockstorage_ip\"${array[$array_size-1]}\"
    echo "blockstorage  = [$blockstorage_ip]" >> $CONFIG_FILE
    
    #default controller
    echo "default_controller = $default_controller" >> $CONFIG_FILE
    
    #waiting primary stop time
    echo "wait_primary_stop_time = 30" >> $CONFIG_FILE
    
    #polling interval
    echo "polling_interval = 1" >> $CONFIG_FILE
    
    #transient_timeout
    echo "transient_timeout = 3" >> $CONFIG_FILE
    echo "make config end" >> $LOG_FILE
    upstart_setting
}


upstart_setting() {
    UPSTART_CONF_FILE=/home/localadmin/controllerHA/controllerHAd.conf
    cp $UPSTART_CONF_FILE /etc/init/.
    start_controller_service
}
start_controller_service() {
    service controllerHAd restart >> $LOG_FILE
    service controllerHAd status >> $LOG_FILE
    install_script_end
}

install_script_end() {
    DATE=`date`
    echo "==========$DATE controllerHA_install script end=============" >> $LOG_FILE   
}
install_script_start
