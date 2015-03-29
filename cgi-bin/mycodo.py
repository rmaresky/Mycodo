#!/usr/bin/python
# -*- coding: utf-8 -*-
#
#  mycodo.py - Read sensors, write log, read configuration file, write
#              configuration file, and modulate relays to regulate temperature
#              and humidity.
#
#  Kyle Gabriel (2012 - 2015)
#
# Start with:
# sudo stdbuf -oL python ./mycodo.py -d | tee /var/log/some.log
# sudo stdbuf -oL python ./mycodo.py -d >> /var/log/some.log 2>&1 &
#

#### Configure Install Directory ####
install_directory = "/var/www/mycodo"


import Adafruit_DHT
import subprocess
import re
import os
import fcntl
import sys
import time
import datetime
import getopt
import RPi.GPIO as GPIO
import ConfigParser
import threading
import rpyc
from rpyc.utils.server import ThreadedServer
from array import *

config_file = "%s/config/mycodo.cfg" % install_directory
sensor_log_file = "%s/log/sensor.log" % install_directory
relay_log_file = "%s/log/relay.log" % install_directory
relay_script = "%s/cgi-bin/relay.sh" % install_directory

lock_directory = "/var/lock/mycodo/"
config_lock = "config.lock"
sensor_log_lock = "sensorlog.lock"
relay_log_lock = "relaylog.lock"

# GPIO pins (BCM numbering) and name of devices attached to relay
relayPin = [0] * 9
relayName = [0] * 9

# Sensor data
chktemp = ''
tempc = ''
humidity = ''
dewpointc = ''
heatindexc =  ''

#PID
relayTemp =''
relayHum = ''
setTemp = ''
setHum = ''
Hum_P = ''
Hum_I = ''
Hum_D = ''
Temp_P = ''
Temp_I = ''
Temp_D = ''
factorHumSeconds = ''
factorTempSeconds = ''

# Control States
tempState = ''
humState = ''
TempOR = ''
HumOR = ''

# Timers
timerSecWriteLog = ''

# Relay overrides
relay1o = ''
relay2o = ''
relay3o = ''
relay4o = ''
relay5o = ''
relay6o = ''
relay7o = ''
relay8o = ''

# Sensor
DHTSensor = ''
DHTPin = ''

# Miscellaneous
server = ''
variableName = ''
variableValue = ''
ClientQue = '0'
ClientArg1 = ''
ClientArg2 = ''
Terminate = False
TAlive = 1
HAlive = 1
p_temp = ''
p_hum = ''

# Threaded server that receives commands from mycodo-client.py
class ComServer(rpyc.Service):
    def exposed_Terminate(self, remoteCommand):
        global ClientQue
        global Terminate
        Terminate = True
        ClientQue = 'TerminateServer'
        return 1
    def exposed_ChangeSensor(self, sensortype, sensorpin, sensorsec):
        global ClientQue
        global DHTSensor
        global DHTPin
        global timerSecWriteLog
        timerSecWriteLog = sensorsec
        DHTSensor = sensortype
        DHTPin = sensorpin
        ClientQue = 'ChangeSensor'
        return 1
    def exposed_ChangeRelay(self, remoteCommand, remoteCommand2):
        global ClientQue
        global ClientArg1
        global ClientArg2
        ClientArg1 = int(float(remoteCommand))
        ClientArg2 = int(float(remoteCommand2))
        ClientQue = 'ChangeRelay'
        return 1
    def exposed_RelayOnSec(self, remoteCommand, remoteCommand2):
        global ClientQue
        global ClientArg1
        global ClientArg2
        ClientArg1 = int(float(remoteCommand))
        ClientArg2 = int(float(remoteCommand2))
        ClientQue = 'RelayOnSec'
        return 1
    def exposed_ChangeOverride(self, tempor, humor):
        global ClientQue
        global TempOR
        global HumOR
        TempOR = tempor
        HumOR = humor
        ClientQue = 'ChangeOverride'
        return 1
    def exposed_ChangeRelayNames(self, relayname1, relayname2, relayname3,
            relayname4, relayname5, relayname6, relayname7, relayname8):
        global ClientQue
        global relayName
        relayName[1] = relayname1
        relayName[2] = relayname2
        relayName[3] = relayname3
        relayName[4] = relayname4
        relayName[5] = relayname5
        relayName[6] = relayname6
        relayName[7] = relayname7
        relayName[8] = relayname8
        ClientQue = 'ChangeRelayNames'
        return 1
    def exposed_ChangeRelayPins(self, relaypin1, relaypin2, relaypin3,
            relaypin4, relaypin5, relaypin6, relaypin7, relaypin8):
        global ClientQue
        global relayPin
        relayPin[1] = relaypin1
        relayPin[2] = relaypin2
        relayPin[3] = relaypin3
        relayPin[4] = relaypin4
        relayPin[5] = relaypin5
        relayPin[6] = relaypin6
        relayPin[7] = relaypin7
        relayPin[8] = relaypin8
        ClientQue = 'ChangeRelayPins'
        return 1
    def exposed_ChangeTempOR(self, tempor):
        global ClientQue
        global TempOR
        TempOR = tempor
        ClientQue = 'ChangeTempOR'
        return 1
    def exposed_ChangeHumOR(self, humor):
        global ClientQue
        global HumOR
        HumOR = humor
        ClientQue = 'ChangeHumOR'
        return 1
    def exposed_ChangeConditionsTemp(self, relaytemp, settemp,
            temp_p, temp_i, temp_d, factortempseconds):
        global ClientQue
        global relayTemp
        global setTemp
        global Temp_P
        global Temp_I
        global Temp_D
        global factorTempSeconds
        relayTemp = relaytemp
        setTemp = settemp
        Temp_P = temp_p
        Temp_I = temp_i
        Temp_D = temp_d
        factorTempSeconds = factortempseconds
        ClientQue = 'ChangeConditionsTemp'
        return 1
    def exposed_ChangeConditionsHum(self, relayhum, sethum,
            hum_p, hum_i, hum_d, factorhumseconds):
        global ClientQue
        global relayHum
        global setHum
        global Hum_P
        global Hum_I
        global Hum_D
        global factorHumSeconds
        relayHum = relayhum
        setHum = sethum
        Hum_P = hum_p
        Hum_I = hum_i
        Hum_D = hum_d
        factorHumSeconds = factorhumseconds
        ClientQue = 'ChangeConditionsHum'
        return 1
    def exposed_WriteSensorLog(self):
        global ClientQue
        ClientQue = 'WriteSensorLog'
        return 1

class ComThread(threading.Thread):
    def run(self):
        global server
        server = ThreadedServer(ComServer, port = 18812)
        server.start()

# PID controller for humidity
class Humidity_PID:
    def __init__(self, P=2.0, I=0.0, D=1.0, Derivator=0, Integrator=0,
            Integrator_max=500, Integrator_min=-500):
        self.Kp=P
        self.Ki=I
        self.Kd=D
        self.Derivator=Derivator
        self.Integrator=Integrator
        self.Integrator_max=Integrator_max
        self.Integrator_min=Integrator_min
        self.set_point=0.0
        self.error=0.0
    def update(self, current_value):
        """Calculate PID output value from reference input and feedback"""
        self.error = self.set_point - current_value
        self.P_value = self.Kp * self.error
        self.D_value = self.Kd * ( self.error - self.Derivator)
        self.Derivator = self.error
        self.Integrator = self.Integrator + self.error
        if self.Integrator > self.Integrator_max:
            self.Integrator = self.Integrator_max
        elif self.Integrator < self.Integrator_min:
            self.Integrator = self.Integrator_min
        self.I_value = self.Integrator * self.Ki
        PID = self.P_value + self.I_value + self.D_value
        return PID
    def setPoint(self, set_point):
        """Initilize the setpoint of PID"""
        self.set_point = set_point
        self.Integrator=0
        self.Derivator=0
    def setIntegrator(self, Integrator):
        self.Integrator = Integrator
    def setDerivator(self, Derivator):
        self.Derivator = Derivator
    def setKp(self,P):
        self.Kp=P
    def setKi(self,I):
        self.Ki=I
    def setKd(self,D):
        self.Kd=D
    def getPoint(self):
        return self.set_point
    def getError(self):
        return self.error
    def getIntegrator(self):
        return self.Integrator
    def getDerivator(self):
        return self.Derivator

# PID controller for temperature
class Temperature_PID:
    def __init__(self, P=2.0, I=0.0, D=1.0, Derivator=0, Integrator=0,
            Integrator_max=500, Integrator_min=-500):
        self.Kp=P
        self.Ki=I
        self.Kd=D
        self.Derivator=Derivator
        self.Integrator=Integrator
        self.Integrator_max=Integrator_max
        self.Integrator_min=Integrator_min
        self.set_point=0.0
        self.error=0.0
    def update(self,current_value):
        """Calculate PID output value from reference input and feedback"""
        self.error = self.set_point - current_value
        self.P_value = self.Kp * self.error
        self.D_value = self.Kd * ( self.error - self.Derivator)
        self.Derivator = self.error
        self.Integrator = self.Integrator + self.error
        if self.Integrator > self.Integrator_max:
            self.Integrator = self.Integrator_max
        elif self.Integrator < self.Integrator_min:
            self.Integrator = self.Integrator_min
        self.I_value = self.Integrator * self.Ki
        PID = self.P_value + self.I_value + self.D_value
        return PID
    def setPoint(self,set_point):
        """Initilize the setpoint of PID"""
        self.set_point = set_point
        self.Integrator=0
        self.Derivator=0
    def setIntegrator(self, Integrator):
        self.Integrator = Integrator
    def setDerivator(self, Derivator):
        self.Derivator = Derivator
    def setKp(self,P):
        self.Kp=P
    def setKi(self,I):
        self.Ki=I
    def setKd(self,D):
        self.Kd=D
    def getPoint(self):
        return self.set_point
    def getError(self):
        return self.error
    def getIntegrator(self):
        return self.Integrator
    def getDerivator(self):
        return self.Derivator

# Displays the program usage
def usage():
    SyncPrint("mycodo.py: Reads temperature and humidity from sensors, "
        "writes log file, and operates relays as a daemon to maintain "
        "set environmental conditions.\n", 1)
    SyncPrint("Usage:   mycodo.py [OPTION]...\n", 1)
    SyncPrint("Example: mycodo.py -w /var/www/mycodo/log/sensor.log", 1)
    SyncPrint("         mycodo.py -c 1 -s 0", 1)
    SyncPrint("         mycodo.py -n relay1Name --value Banana", 1)
    SyncPrint("         mycodo.py --daemon\n", 1)
    SyncPrint("Options:", 1)
    SyncPrint("    -c, --change=RELAY", 1)
    SyncPrint("           Change the state of a relay (--state required)", 1)
    SyncPrint("        --state=[ON/OFF/X]", 1)
    SyncPrint("           Change the state of RELAY to ON, OFF, or (X) number of seconds on", 1)
    SyncPrint("    -d, --daemon", 1)
    SyncPrint("           Start program as daemon that monitors conditions and modulates relays", 1)
    SyncPrint("    -h, --help", 1)
    SyncPrint("           Display this help and exit", 1)
    SyncPrint("    -n, --name=VARIABLE", 1)
    SyncPrint("           Change the VALUE of a single VARIABLE (--value required)", 1)
    SyncPrint("        --value=VALUE", 1)
    SyncPrint("           Change the VALUE of variable NAME (-n required)", 1)
    SyncPrint("    -p, --pin", 1)
    SyncPrint("           Display status of the GPIO pins (HIGH or LOW)", 1)
    SyncPrint("    -r  --read=[SENSOR/CONFIG]", 1)
    SyncPrint("           Read and display sensor data or config settings", 1)
    SyncPrint("    -s, --set setTemp setHum TempOR HumOR", 1)
    SyncPrint("           Change operating parameters (must give all options as int, overrides must be 0 or 1)", 1)
    SyncPrint("    -w, --write=FILE", 1)
    SyncPrint("           Write sensor data to log file\n", 1)

# Checks user options and arguments for validity
def menu():
    if len(sys.argv) == 1: # No arguments given
        usage()
        sys.exit(1)

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'c:dhpr:s:tn:w',
            ["change=", "daemon", "help", "name=", "pin",
            "read=", "set=", "state=", "value=", "write="])
    except getopt.GetoptError as err:
        print(err) # will SyncPrint("option -a not recognized"
        usage()
        sys.exit(2)
    for opt, arg in opts:
        if opt in ("-c", "--change"):
            if not RepresentsInt(arg) or \
                    int(float(arg)) > 8 or \
                    int(float(arg)) < 1:
                SyncPrint("Error: --change only accepts integers 1 though 8", 1)
                sys.exit(1)
            else:
                global relaySelect
                relaySelect = arg
        elif opt == "--state":
            if RepresentsInt(arg) and int(float(arg)) > 1 or \
                    (arg == 'OFF' or arg == 'ON'):
                ReadCfg(0)
                if arg == 'ON':
                    SyncPrint("%s [GPIO Write] Relay %s ON" % (
                        Timestamp(), relaySelect), 1)
                    ChangeRelay(int(float(relaySelect)), 0)
                    GPIORead()
                    sys.exit(0)
                if arg == 'OFF':
                    SyncPrint("%s [GPIO Write] Relay %s OFF" % (
                        Timestamp(), relaySelect), 1)
                    ChangeRelay(int(float(relaySelect)), 1)
                    GPIORead()
                    sys.exit(0)
                elif int(float(arg)) > 1:
                    SyncPrint("%s [GPIO Write] Relay %s ON for %s seconds" % (
                        Timestamp(), int(float(arg))), 1)
                    RelayOnDuration(int(float(relaySelect)), int(float(arg)))
                    sys.exit(0)
                else:
                    SyncPrint("--state only accepts ON, OFF, integers > 1", 1)
                    usage()
                    sys.exit(1)
        elif opt in ("-d", "--daemon"):
            Daemon()
            sys.exit(0)
        elif opt in ("-h", "--help"):
            usage()
            sys.exit(0)
        elif opt in ("-n", "--name"):
            global variableName
            variableName = arg
        elif opt == "--value":
            global variableValue
            variableValue = arg
            if not CheckVariableName():
                SyncPrint("Error: Variable '%s' does not exist" 
                    % variableName, 1)
                sys.exit(1)
            else:
                SyncPrint("%s [Change Value] Changing variable '%s' value to %s"
                    % (Timestamp(), variableName, variableValue), 1)
                ReadCfg(0)
                globals()[variableName] = variableValue
                WriteCfg()
                SyncPrint("%s [Change Value] Variable '%s' value changed to %s" 
                    % (Timestamp(), variableName, variableValue), 1)
                sys.exit(0)
        elif opt in ("-p", "--pin"):
            ReadCfg(0)
            GPIORead()
            sys.exit(0)
        elif opt in ("-r", "--read"):
            if arg == 'SENSOR':
                ReadSensors(0)
                sys.exit(0)
            elif arg == 'CONFIG':
                ReadCfg(0)
                sys.exit(0)
            else:
                SyncPrint("Error: Invalid option for --read", 1)
                usage()
                sys.exit(1)
        elif opt in ("-s", "--set"):
            if len(sys.argv) != 6:
                SyncPrint("Error: Too many/not enough options", 1)
                sys.exit(1)
            elif not RepresentsFloat(sys.argv[2]) and \
                    not RepresentsFloat(sys.argv[3]) and \
                    not RepresentsInt(sys.argv[4]) and \
                    not RepresentsInt(sys.argv[5]):
                SyncPrint("Error: --set: temperature and humidity requires one decimal place and overrides need to be either 1 or 0", 1)
                sys.exit(1)
            elif (sys.argv[4] != '0' and sys.argv[4] != '1') or \
                    (sys.argv[5] != '0' and sys.argv[5] != '1'):
                SyncPrint("Error: Last option of --set must be 0 or 1", 1)
                sys.exit(0)
            SyncPrint("%s [Set Conditions] Desired values: "
                    "setTemp: %s, setHum: %s, TempOR: %s, HumOR: %s" 
                    % (Timestamp(),
                    sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]), 1)
            ReadCfg(0)
            global setTemp
            global setHum
            global TempOR
            global HumOR
            setTemp = int(float(sys.argv[2]))
            setHum = int(float(sys.argv[3]))
            TempOR = int(float(sys.argv[4]))
            HumOR = int(float(sys.argv[5]))
            WriteCfg()
            SyncPrint("%s [Set Conditions] New Values: "
                "setTemp: %.1f°C, setHum: %.1f%%, TempOR: %s, HumOR: %s" 
                % (Timestamp(), setTemp, setHum, TempOR, HumOR), 1)
            sys.exit(0)
        elif opt in ("-w", "--write"):
            global sensor_log_file
            if arg == '':
                SyncPrint("%s [Write Log] No file specified, using default: %s" 
                    % (Timestamp(), sensor_log_file), 1)
            else:
                sensor_log_file = arg
            ReadSensors(0)
            WriteSensorLog()
            sys.exit(0)
        else:
            assert False, "Fail"

# Main loop that reads sensors, modifies relays based on sensor values, writes
# sensor/relay logs, and receives/executes commands from mycodo-client.py
def Daemon():
    global server
    global HAlive
    global TAlive
    global ClientQue
    
    SyncPrint("%s [Daemon] Daemon Started" % Timestamp(), 1)
    SyncPrint("%s [Communication Server] Starting Thread"
        % Timestamp(), 1)
    ct = ComThread()
    ct.daemon = True
    ct.start()

    SyncPrint("%s [Daemon] Initial configuration read to set variables"
        % Timestamp(), 1)
    ReadCfg(1)
    ReadSensors(0)
    timerSensorLog = int(time.time()) + timerSecWriteLog
   
    tm = threading.Thread(target = TemperatureMonitor)   
    tm.daemon = True
    tm.start()
    
    hm = threading.Thread(target = HumidityMonitor)
    hm.daemon = True
    hm.start()

    while True: # Main loop of the daemon
        if ClientQue != '0': # Run remote commands issued by mycodo-client.py
            if ClientQue == 'ChangeSensor':
                SyncPrint("%s [Client command] Change DHT: "
                    "Sensor: %s, Pin %s: LogSec: %s" % (Timestamp(), 
                    DHTSensor, DHTPin, timerSecWriteLog), 1)
                WriteCfg()
            elif ClientQue == 'WriteSensorLog':
                SyncPrint("%s [Client command] Write Sensor Log" % (
                    Timestamp()), 1)
                ReadSensors(0)
                WriteSensorLog()
            elif ClientQue == 'ChangeRelay':
                SyncPrint("%s [Client command] Set Relay %s GPIO to %s" % (
                    Timestamp(), ClientArg1, ClientArg1), 1)
                ChangeRelay(ClientArg1, ClientArg2)
                GPIORead()
            elif ClientQue == 'ChangeRelayNames':
                SyncPrint("%s [Client command] Change Relay Names: 1 %s, 2 %s, 3 %s, 4 %s, 5 %s, 6 %s, 7 %s, 8 %s" % (
                    Timestamp(),
                    relayName[1], relayName[2], relayName[3], relayName[4],
                    relayName[5], relayName[6], relayName[7], relayName[8]), 1)
                WriteCfg()
            elif ClientQue == 'ChangeRelayPins':
                SyncPrint("%s [Client command] Change Relay Pins: 1 %s, 2 %s, 3 %s, 4 %s, 5 %s, 6 %s, 7 %s, 8 %s" % (
                    Timestamp(),
                    relayPin[1], relayPin[2], relayPin[3], relayPin[4],
                    relayPin[5], relayPin[6], relayPin[7], relayPin[8]), 1)
                WriteCfg()
            elif ClientQue == 'ChangeTempOR':
                SyncPrint("%s [Client command] Change Temperature Override to %s" % (
                    Timestamp(), TempOR), 1)
                WriteCfg()
                
                if not TempOR:
                    if tm.isAlive():
                        SyncPrint("%s [Daemon] Restarting Temperature PID thread" 
                            % Timestamp(), 1)
                        TAlive = 0
                        while TAlive != 2:
                            time.sleep(0.1)
                        TAlive = 1
                    tm = threading.Thread(target = TemperatureMonitor)  
                    tm.daemon = True
                    tm.start()
            elif ClientQue == 'ChangeHumOR':
                SyncPrint("%s [Client command] Change Humidity Override to %s" % (
                    Timestamp(), HumOR), 1)
                WriteCfg()
                
                if not HumOR:
                    SyncPrint("%s [Daemon] Restarting Humidity PID thread" 
                        % Timestamp(), 1)
                    HAlive = 0
                    while HAlive != 2:
                        time.sleep(0.1)
                    HAlive = 1
                    hm = threading.Thread(target = HumidityMonitor)
                    hm.daemon = True
                    hm.start()
            elif ClientQue == 'ChangeConditionsTemp':
                SyncPrint("%s [Client command] Change Temperature: relay: %s set: %.1f°C" % (
                    Timestamp(), relayTemp, setTemp), 1)
                SyncPrint("%s [Client command] Change Temp PID: P: %.1f, I: %.1f D: %.1f, Sec: %s" % (
                    Timestamp(), Temp_P, Temp_I, Temp_D,
                    factorTempSeconds), 1)
                WriteCfg()
                SyncPrint("%s [Daemon] Restarting Temperature PID thread" 
                    % Timestamp(), 1)
                TAlive = 0
                while TAlive != 2:
                    time.sleep(0.1)
                TAlive = 1
                tm = threading.Thread(target = TemperatureMonitor)  
                tm.daemon = True
                tm.start()
            elif ClientQue == 'ChangeConditionsHum':
                SyncPrint("%s [Client command] Change Humidity: relay: %s, set: %.1f" 
                    % (Timestamp(), relayHum, setHum), 1)
                SyncPrint("%s [Client command] Change PID: Hum: P: %.1f, I: %.1f D: %.1f, Sec: %s" 
                    % (Timestamp(), Hum_P, Hum_I, Hum_D, 
                    factorHumSeconds), 1)
                WriteCfg()
                SyncPrint("%s [Daemon] Restarting Humidity PID thread" 
                    % Timestamp(), 1)
                HAlive = 0
                while HAlive != 2:
                    time.sleep(0.1)
                HAlive = 1
                hm = threading.Thread(target = HumidityMonitor)
                hm.daemon = True
                hm.start()
            elif ClientQue == 'RelayOnSec':
                SyncPrint("%s [Client command] Set Relay %s on for %s seconds"
                    % (Timestamp(), ClientArg1, ClientArg2), 1)
                RelayOnDuration(ClientArg1, ClientArg2)
            elif ClientQue == 'TerminateServer':
                SyncPrint("%s [Client command] Terminate threads and shut down"
                    % Timestamp(), 1)
                TAlive = 0
                while TAlive != 2:
                    time.sleep(0.1)
                HAlive = 0
                while HAlive != 2:
                    time.sleep(0.1)
                server.close()
                SyncPrint("%s [Daemon] Exiting Python" % Timestamp(), 1)
                sys.exit(0)
            ClientQue = '0'
        
        # Write sensor log
        if int(time.time()) > timerSensorLog:
            SyncPrint("%s [Timer Expiration] Run every %s seconds: Write sensor log" 
                % (Timestamp(), timerSecWriteLog), 1)
            ReadSensors(0)
            WriteSensorLog()
            timerSensorLog = int(time.time()) + timerSecWriteLog

        time.sleep(1)

# Temperature modulation by PID control
def TemperatureMonitor():
    global tempState
    global TAlive
    timerTemp = 0
    PIDTemp = 0
    SyncPrint("%s [PID Temperature] Starting Thread"
                    % Timestamp(), 1)
    if (tempc < setTemp): tempState = 0
    else: tempState = 1
    p_temp = Temperature_PID(Temp_P, Temp_I, Temp_D)
    p_temp.setPoint(setTemp)
    
    while TAlive == 1:
        if TempOR == 0:
            if int(time.time()) > timerTemp:
                SyncPrint("%s [PID Temperature] Reading temperature..."
                    % Timestamp(), 1)
                ReadSensors(1)
                if (tempc >= setTemp): tempState = 1
                if (tempc < setTemp): tempState = 0
                if (tempState == 0):
                    PIDTemp = round(p_temp.update(float(tempc)), 1)
                    SyncPrint("%s [PID Temperature] Temperature (%.1f°C) < setTemp (%.1f°C)" 
                        % (Timestamp(), tempc, setTemp), 1)
                    SyncPrint("%s [PID Temperature] PID = %.1f (seconds)" 
                        % (Timestamp(), PIDTemp), 1)
                    if (PIDTemp > 0 and tempc < setTemp):
                        rod = threading.Thread(target = RelayOnDuration, 
                            args = (relayTemp, PIDTemp,))
                        rod.start()
                    timerTemp = int(time.time()) + PIDTemp + factorTempSeconds
                else:
                    SyncPrint("%s [PID Temperature] Temperature (%.1f°C) > setTemp (%.1f°C), waiting 60 seconds" 
                        % (Timestamp(), tempc, setTemp), 1)
                    p_temp.update(float(tempc))
                    timerTemp = int(time.time()) + 60
    SyncPrint("%s [PID Temperature] Shutting Down Thread" % Timestamp(), 1)
    TAlive = 2

# Humidity modulation by PID control
def HumidityMonitor():
    global humState
    global HAlive
    timerHum = 0
    PIDHum = 0

    SyncPrint("%s [PID Humidity] Starting Thread" 
        % Timestamp(), 1)
    if (humidity < setHum): humState = 0
    else: humState = 1
    p_hum = Humidity_PID(Hum_P, Hum_I, Hum_D)
    p_hum.setPoint(setHum)

    while HAlive == 1:
        if HumOR == 0:
            if int(time.time()) > timerHum:
                SyncPrint("%s [PID Humidity] Reading humidity..." 
                    % Timestamp(), 1)
                ReadSensors(1)
                if (humidity >= setHum): humState = 1
                if (humidity < setHum): humState = 0
                if (humState == 0):
                    PIDHum = round(p_hum.update(float(humidity)), 1)
                    SyncPrint("%s [PID Humidity] Humidity (%.1f%%) < setHum (%.1f%%)" 
                        % (Timestamp(), humidity, setHum), 1)
                    SyncPrint("%s [PID Humidity] PID = %.1f (seconds)" 
                        % (Timestamp(), PIDHum), 1)
                    if (PIDHum > 0 and humidity < setHum):
                        rod = threading.Thread(
                            target = RelayOnDuration, args=(relayHum, PIDHum,))
                        rod.start()
                    timerHum = int(time.time()) + PIDHum + factorTempSeconds
                else:
                    SyncPrint("%s [PID Humidity] Humidity (%.1f%%) > setHum (%.1f%%), waiting 60 seconds" 
                        % (Timestamp(), humidity, setHum), 1)
                    p_hum.update(float(humidity))
                    timerHum = int(time.time()) + 60
    SyncPrint("%s [PID Humidity] Shutting Down Thread" % Timestamp(), 1)
    HAlive = 2

# Set GPIO LOW (= relay ON) for a specific duration
def RelayOnDuration(relay, seconds):
    if GPIO.input(relayPin[relay]) == 1:
        WriteRelayLog(relay, seconds)
        SyncPrint("%s [Relay Duration] Relay %s (%s) ON for %s seconds" 
            % (Timestamp(), relay, relayName[relay], seconds), 1)
        GPIO.output(relayPin[relay], 0)
        time.sleep(seconds)
        GPIO.output(relayPin[relay], 1)
        SyncPrint("%s [Relay Duration] Relay %s (%s) OFF (was ON for %s sec)"
            % (Timestamp(), relay, relayName[relay], seconds), 1)
        return 1
    else:
        SyncPrint("%s [Relay Duration] Abort: Requested relay %s (%s) ON for %s seconds, but it's already on!" 
            % (Timestamp(), relay, relayName[relay], seconds), 1)
        return 0

# Append sensor data to the log file
def WriteSensorLog():
    sensor_lock_path = lock_directory + sensor_log_lock
    config = ConfigParser.RawConfigParser()

    if not os.path.exists(lock_directory):
        os.makedirs(lock_directory)

    waitingForLock = 1
    errorOnce = 1
    lockWaitCount = 1
    while waitingForLock and not Terminate:
        if not lockFile(sensor_lock_path) and not Terminate:
            if errorOnce:
                SyncPrint("%s [Write Sensor Log] Cannot gain lock (already locked): Waiting to gain lock..." 
                    % Timestamp(), 1)
                errorOnce = 0
            if lockWaitCount == 60:
                SyncPrint("%s [Write Sensor Log] 60 seconds waiting to gain lock (too long): Breaking lock."
                    % Timestamp(), 1)
                os.remove(sensor_lock_path)
                lockWaitCount+=1
            if lockWaitCount % 10 == 0:
                SyncPrint("%s [Write Sensor Log] Waiting to gain lock for %s seconds..." 
                    % (Timestamp(), lockWaitCount), 1)
            time.sleep(1)
            lockWaitCount+=1
        elif not Terminate:
            waitingForLock = 0
            SyncPrint("%s [Write Sensor Log] Gained lock: %s" 
                % (Timestamp(), sensor_lock_path), 1)
            try:
                open(sensor_log_file, 'ab').write('{0} {1:.1f} {2:.1f} {3:.1f}\n'.format(
                    datetime.datetime.now().strftime("%Y %m %d %H %M %S"), 
                    tempc, humidity, dewpointc))
                SyncPrint("%s [Write Sensor Log] Data appended to %s" 
                    % (Timestamp(), sensor_log_file), 1)
            except:
                SyncPrint("%s [Write Sensor Log] Unable to append data to %s" 
                    % (Timestamp(), sensor_log_file), 1)
                
    if os.path.isfile(sensor_lock_path):
        SyncPrint("%s [Write Sensor Log] Removing lock: %s" 
            % (Timestamp(), sensor_lock_path), 1)
        os.remove(sensor_lock_path)
    else:
        SyncPrint("%s [Write Sensor Log] Unable to remove lock file %s: It doesn't exist!" 
            % (Timestamp(), sensor_lock_path), 1)

# Append the duration the relay has been on to the log file
def WriteRelayLog(relayNumber, relaySeconds):
    relay_lock_path = lock_directory + relay_log_lock
    config = ConfigParser.RawConfigParser()

    if not os.path.exists(lock_directory):
        os.makedirs(lock_directory)

    waitingForLock = 1
    errorOnce = 1
    lockWaitCount = 1
    while waitingForLock and not Terminate:
        if not lockFile(relay_lock_path) and not Terminate:
            if errorOnce:
                SyncPrint("%s [Write Relay Log] Cannot gain lock: Already locked: Waiting to gain lock..." 
                    % Timestamp(), 1)
                errorOnce = 0
            if lockWaitCount == 60:
                SyncPrint("%s [Write Relay Log] 60 sec waiting to gain lock (too long): Breaking lock." 
                    % Timestamp(), 1)
                os.remove(relay_lock_path)
                lockWaitCount+=1
            if lockWaitCount % 10 == 0:
                SyncPrint("%s [Write Relay Log] Waiting to gain lock for %s seconds..." 
                    % (Timestamp(), lockWaitCount), 1)
            time.sleep(1)
            lockWaitCount+=1
        elif not Terminate:
            waitingForLock = 0
            SyncPrint("%s [Write Relay Log] Gained lock: %s" 
                % (Timestamp(), relay_lock_path), 1)
            relay = [0] * 9
            for n in range(1, 9):
                if n == relayNumber:
                    relay[relayNumber] = relaySeconds
            try:
                open(relay_log_file, 'ab').write('{0} {1} {2} {3} {4} {5} {6} {7} {8}\n'.format(
                    datetime.datetime.now().strftime("%Y %m %d %H %M %S"), 
                    relay[1], relay[2], relay[3], relay[4],
                    relay[5], relay[6], relay[7], relay[8]))
                SyncPrint("%s [Write Relay Log] Data appended to %s" 
                    % (Timestamp(), relay_log_file), 1)
            except:
                SyncPrint("%s [Write Relay Log] Unable to append data to %s" 
                    % (Timestamp(), relay_log_file), 1)
                
    if os.path.isfile(relay_lock_path):
        SyncPrint("%s [Write Relay Log] Removing lock file %s" 
            % (Timestamp(), relay_lock_path), 1)
        os.remove(relay_lock_path)
    else:
        SyncPrint("%s [Write Relay Log] Unable to remove lock file %s: It doesn't exist!" 
            % (Timestamp(), relay_lock_path), 1)

# Read the temperature and humidity from the DHT22 sensor
def ReadSensors(silent):
    global tempc
    global humidity
    global dewpointc
    global heatindexc
    global chktemp
    chktemp = 1
    
    if (DHTSensor == 'DHT11'): sensor = Adafruit_DHT.DHT11
    elif (DHTSensor == 'DHT22'): sensor = Adafruit_DHT.DHT22
    elif (DHTSensor == 'AM2302'): sensor = Adafruit_DHT.AM2302

    if not silent and not Terminate:
        SyncPrint("%s [Read Sensors] Taking first Temperature/humidity reading" 
            % Timestamp(), 1)
    if not Terminate:
        humidity2, tempc2 = Adafruit_DHT.read_retry(sensor, DHTPin)
        if not silent:
            SyncPrint("%s [Read Sensors] %.1f°C, %.1f%%" 
                % (Timestamp(), tempc2, humidity2), 1)
    if not Terminate:
        time.sleep(2);
        if not silent: 
            SyncPrint("%s [Read Sensors] Taking second Temperature/humidity reading" 
                % Timestamp(), 1)

    while chktemp and not Terminate:
        if not Terminate:
            humidity, tempc = Adafruit_DHT.read_retry(sensor, DHTPin)
        if not silent and not Terminate: 
            SyncPrint("%s [Read Sensors] %.1f°C, %.1f%%" 
                % (Timestamp(), tempc, humidity), 1)
            SyncPrint("%s [Read Sensors] Differences: %.1f°C, %.1f%%" 
                % (Timestamp(), abs(tempc2-tempc), abs(humidity2-humidity)), 1)
        if abs(tempc2-tempc) > 1 or abs(humidity2-humidity) > 1 and not Terminate:
            tempc2 = tempc
            humidity2 = humidity
            chktemp = 1
            if not silent:
                SyncPrint("%s [Read Sensors] Successive readings > 1 difference: Rereading" 
                    % Timestamp(), 1)
            time.sleep(2)
        elif not Terminate:
            chktemp = 0
            if not silent: 
                SyncPrint("%s [Read Sensors] Successive readings < 1 difference: keeping." 
                    % Timestamp(), 1)
            tempf = float(tempc)*9.0/5.0 + 32.0
            dewpointc = tempc - ((100-humidity) / 5)
            #dewpointf = dewpointc * 9 / 5 + 32
            #heatindexf =  -42.379 + 2.04901523 * tempf + 10.14333127 * humidity - 0.22475541 * tempf * humidity - 6.83783 * 10**-3 * tempf**2 - 5.481717 * 10**-2 * humidity**2 + 1.22874 * 10**-3 * tempf**2 * humidity + 8.5282 * 10**-4 * tempf * humidity**2 - 1.99 * 10**-6 * tempf**2 * humidity**2
            #heatindexc = (heatindexf - 32) * (5 / 9)
            if not silent: 
                SyncPrint("%s [Read Sensors] Temp: %.2f°C, Hum: %.2f%%, DP: %.2f°C" 
                    % (Timestamp(), tempc, humidity, dewpointc), 1)

# Read variables from the configuration file
def ReadCfg(silent):
    global config_file
    global DHTSensor
    global DHTPin
    global relayName
    global relayPin
    global relayTemp
    global relayHum
    global setTemp
    global setHum
    global TempOR
    global HumOR
    global Hum_P
    global Hum_I
    global Hum_D
    global Temp_P
    global Temp_I
    global Temp_D
    global factorHumSeconds
    global factorTempSeconds
    global tempState
    global humState
    global relay1o
    global relay2o
    global relay3o
    global relay4o
    global relay5o
    global relay6o
    global relay7o
    global relay8o
    global timerSecWriteLog

    config = ConfigParser.RawConfigParser()
    config.read(config_file)
    
    DHTSensor = config.get('Sensor', 'dhtsensor')
    DHTPin = config.getint('Sensor', 'dhtpin')

    relayName[1] = config.get('RelayNames', 'relay1name')
    relayName[2] = config.get('RelayNames', 'relay2name')
    relayName[3] = config.get('RelayNames', 'relay3name')
    relayName[4] = config.get('RelayNames', 'relay4name')
    relayName[5] = config.get('RelayNames', 'relay5name')
    relayName[6] = config.get('RelayNames', 'relay6name')
    relayName[7] = config.get('RelayNames', 'relay7name')
    relayName[8] = config.get('RelayNames', 'relay8name')

    relayPin[1] = config.getint('RelayPins', 'relay1pin')
    relayPin[2] = config.getint('RelayPins', 'relay2pin')
    relayPin[3] = config.getint('RelayPins', 'relay3pin')
    relayPin[4] = config.getint('RelayPins', 'relay4pin')
    relayPin[5] = config.getint('RelayPins', 'relay5pin')
    relayPin[6] = config.getint('RelayPins', 'relay6pin')
    relayPin[7] = config.getint('RelayPins', 'relay7pin')
    relayPin[8] = config.getint('RelayPins', 'relay8pin')

    relayTemp = config.getint('PID', 'relaytemp')
    relayHum = config.getint('PID', 'relayhum')
    setTemp = config.getfloat('PID', 'settemp')
    setHum = config.getfloat('PID', 'sethum')
    TempOR = config.getint('PID', 'tempor')
    HumOR = config.getint('PID', 'humor')
    Hum_P = config.getfloat('PID', 'hum_p')
    Hum_I = config.getfloat('PID', 'hum_i')
    Hum_D = config.getfloat('PID', 'hum_d')
    Temp_P = config.getfloat('PID', 'temp_p')
    Temp_I = config.getfloat('PID', 'temp_i')
    Temp_D = config.getfloat('PID', 'temp_d')
    factorHumSeconds = config.getint('PID', 'factorhumseconds')
    factorTempSeconds = config.getint('PID', 'factortempseconds')
    
    tempState = config.getint('States', 'tempstate')
    humState = config.getint('States', 'humstate')
    relay1o = config.getint('States', 'relay1o')
    relay2o = config.getint('States', 'relay2o')
    relay3o = config.getint('States', 'relay3o')
    relay4o = config.getint('States', 'relay4o')
    relay5o = config.getint('States', 'relay5o')
    relay6o = config.getint('States', 'relay6o')
    relay7o = config.getint('States', 'relay7o')
    relay8o = config.getint('States', 'relay8o')
    timerSecWriteLog = config.getint('States', 'timersecwritelog')

    if not silent:
        SyncPrint("%s [Read Config] setTemp: %.1f°C, setHum: %.1f%%, TempOR: %s, HumOR: %s" 
            % (Timestamp(), setTemp, setHum, TempOR, HumOR), 1)
        SyncPrint("%s [Read Config] RelayNum[Name][Pin]:" % Timestamp(), 0)
        for x in range(1,9):
            if x == 5:
                SyncPrint("\n%s [Read Config] RelayNum[Name][Pin]:" 
                    % Timestamp(), 0)
            if relayPin[x] < 10:
                SyncPrint("%s[%s][%s ]" % (x, relayName[x], relayPin[x]), 0)
            else:
                SyncPrint("%s[%s][%s]" % (x, relayName[x], relayPin[x]), 0)
        SyncPrint("\n%s [Read Config] %s %s %s %s %s %s %s %s %s %s %s" 
            % (Timestamp(), tempState, humState, 
            relay1o, relay2o, relay3o, relay4o, 
            relay5o, relay6o, relay7o, relay8o, 
            timerSecWriteLog), 1)

# Write variables to configuration file
def WriteCfg():
    config_lock_path = lock_directory + config_lock
    config = ConfigParser.RawConfigParser()

    if not os.path.exists(lock_directory):
        os.makedirs(lock_directory)

    waitingForLock = 1
    errorOnce = 1
    lockWaitCount = 1
    while waitingForLock:
        if not lockFile(config_lock_path):
            if errorOnce:
                SyncPrint("%s [Write Config] Cannot gain lock: Already locked: Waiting to gain lock..."
                    % Timestamp(), 1)
                errorOnce = 0
            if lockWaitCount == 60:
                SyncPrint("%s [Write Config] 60 sec waiting to gain lock: Breaking lock." 
                    % Timestamp(), 1)
                os.remove(config_lock_path)
                lockWaitCount+=1
            if lockWaitCount % 10 == 0:
                SyncPrint("%s [Write Config] Waiting to gain lock for %s seconds..." 
                    % (Timestamp(), lockWaitCount), 1)
            time.sleep(1)
            lockWaitCount+=1
        else:
            waitingForLock = 0
            SyncPrint("%s [Write Config] Gained lock: %s" 
                % (Timestamp(), config_lock_path), 1)
            SyncPrint("%s [Write Config] Writing config file %s" 
                % (Timestamp(), config_file), 1)
            
            config.add_section('Sensor')
            config.set('Sensor', 'dhtsensor', DHTSensor)
            config.set('Sensor', 'dhtpin', DHTPin)
            
            config.add_section('RelayNames')
            config.set('RelayNames', 'relay1name', relayName[1])
            config.set('RelayNames', 'relay2name', relayName[2])
            config.set('RelayNames', 'relay3name', relayName[3])
            config.set('RelayNames', 'relay4name', relayName[4])
            config.set('RelayNames', 'relay5name', relayName[5])
            config.set('RelayNames', 'relay6name', relayName[6])
            config.set('RelayNames', 'relay7name', relayName[7])
            config.set('RelayNames', 'relay8name', relayName[8])
            
            config.add_section('RelayPins')
            config.set('RelayPins', 'relay1pin', relayPin[1])
            config.set('RelayPins', 'relay2pin', relayPin[2])
            config.set('RelayPins', 'relay3pin', relayPin[3])
            config.set('RelayPins', 'relay4pin', relayPin[4])
            config.set('RelayPins', 'relay5pin', relayPin[5])
            config.set('RelayPins', 'relay6pin', relayPin[6])
            config.set('RelayPins', 'relay7pin', relayPin[7])
            config.set('RelayPins', 'relay8pin', relayPin[8])

            config.add_section('PID')
            config.set('PID', 'relaytemp', relayTemp)
            config.set('PID', 'relayhum', relayHum)
            config.set('PID', 'tempor', TempOR)
            config.set('PID', 'humor', HumOR)
            config.set('PID', 'settemp', setTemp)
            config.set('PID', 'sethum', setHum)
            config.set('PID', 'hum_p', Hum_P)
            config.set('PID', 'hum_i', Hum_I)
            config.set('PID', 'hum_d', Hum_D)
            config.set('PID', 'temp_p', Temp_P)
            config.set('PID', 'temp_i', Temp_I)
            config.set('PID', 'temp_d', Temp_D)
            config.set('PID', 'factorhumseconds', factorHumSeconds)
            config.set('PID', 'factortempseconds', factorTempSeconds)

            config.add_section('States')
            config.set('States', 'tempstate', tempState)
            config.set('States', 'humstate', humState)
            config.set('States', 'relay1o', relay1o)
            config.set('States', 'relay2o', relay2o)
            config.set('States', 'relay3o', relay3o)
            config.set('States', 'relay4o', relay4o)
            config.set('States', 'relay5o', relay5o)
            config.set('States', 'relay6o', relay6o)
            config.set('States', 'relay7o', relay7o)
            config.set('States', 'relay8o', relay8o)
            config.set('States', 'timersecwritelog', timerSecWriteLog)

            with open(config_file, 'wb') as configfile:
                config.write(configfile)

    if os.path.isfile(config_lock_path):
        SyncPrint("%s [Write Config] Removing lock file %s" 
            % (Timestamp(), config_lock_path), 1)
        os.remove(config_lock_path)
    else:
        SyncPrint("%s [Write Config] Unable to remove lock file %s: It doesn't exist!" 
            % (Timestamp(), config_lock_path), 1)

# Change GPIO (Select) to a specific state (State)
def ChangeRelay(Select, State):
    SyncPrint("%s [GPIO Write] Setting relay %s (%s) to %s (was %s)" 
        % (Timestamp(), Select, relayName[Select], 
        State, GPIO.input(relayPin[Select])), 1)
    GPIO.output(relayPin[Select], State)

# Initialize GPIO
def GPIOSetup():
    SyncPrint("%s [GPIO Initialize] Set GPIO mode to BCM numbering, all as output" 
        % Timestamp(), 1)
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(relayPin[1], GPIO.OUT)
    GPIO.setup(relayPin[2], GPIO.OUT)
    GPIO.setup(relayPin[3], GPIO.OUT)
    GPIO.setup(relayPin[4], GPIO.OUT)
    GPIO.setup(relayPin[5], GPIO.OUT)
    GPIO.setup(relayPin[6], GPIO.OUT)
    GPIO.setup(relayPin[7], GPIO.OUT)
    GPIO.setup(relayPin[8], GPIO.OUT)

# Read states (HIGH/LOW) of GPIO pins
def GPIORead():
    SyncPrint("%s [GPIO Read]" % Timestamp(), 0)
    for x in range(1, 9):
        SyncPrint("Relay %s:" % x, 0)
        if GPIO.input(relayPin[x]): SyncPrint("OFF,", 0)
        else: SyncPrint("ON, ", 0)
        if x == 4: SyncPrint("\n%s [GPIO Read]" % Timestamp(), 0)
        if x == 8: SyncPrint("", 1)

# all terminal/log output is piped through to ensure prints are synchronized
def SyncPrint(msg, newline):
    thread_name = threading.current_thread().name
    if newline: line = '%s\n' % msg
    else: line = '%s' % msg
    print >>sys.stderr, line, # Trailing , indicates no implicit end-of-line

# Lock file to prevent other instances from writing while file is open
def lockFile(lockfile):
    fd = os.open(lockfile, os.O_CREAT | os.O_TRUNC | os.O_WRONLY)
    try: # Request exclusive (EX) non-blocking (NB) advisory lock.
        fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except IOError:
        return False
    return True

# Check if string represents an integer value
def RepresentsInt(s):
    try: 
        int(s)
        return True
    except ValueError:
        return False
        
# Check if string represents a float value
def RepresentsFloat(s):
    try: 
        float(s)
        return True
    except ValueError:
        return False

# Check if a variable name in config_file matches a string
def CheckVariableName():
    namesOfVariables = [
    'tempc',
    'humidity',
    'setTemp',
    'setHum',
    'TempOR',
    'HumOR',
    'tempState',
    'humState',
    'relay1o',
    'relay2o',
    'relay3o',
    'relay4o',
    'relay5o',
    'relay6o',
    'relay7o',
    'relay8o',
    'timerSecWriteLog',
    'Hum_P',
    'Hum_I',
    'Hum_D',
    'Temp_P',
    'Temp_I',
    'Temp_D',
    'factorHumSeconds',
    'factorTempSeconds',
    'relay1Pin',
    'relay2Pin',
    'relay3Pin',
    'relay4Pin',
    'relay5Pin',
    'relay6Pin',
    'relay7Pin',
    'relay8Pin',
    'relay1Name',
    'relay2Name',
    'relay3Name',
    'relay4Name',
    'relay5Name',
    'relay6Name',
    'relay7Name',
    'relay8Name',]

    for variable in namesOfVariables:
        if variableName == variable:
            return 1
    return 0

# Timestamp format used in sensor and relay logs
def Timestamp():
    return datetime.datetime.fromtimestamp(time.time()).strftime('%Y %m %d %H %M %S')

ReadCfg(1)
GPIOSetup()
menu()
usage()
sys.exit(0)