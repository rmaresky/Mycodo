# coding=utf-8

import argparse
import os
import smbus
import time
import timeit
import RPi.GPIO as GPIO


class TCA9548A(object):
    def __init__(self, address=0x70):
        self.i2c_address = address
        if GPIO.RPI_INFO['P1_REVISION'] in [2, 3]:
            self.I2C_bus_number = 1
        else:
            self.I2C_bus_number = 0
        self.bus = smbus.SMBus(self.I2C_bus_number)


    def setup(self, channel):
        try:
            self.bus.write_byte(self.i2c_address, channel)
            return 1, "Success"
        except Exception as msg:
            return 0, "Fail: {}".format(msg)


    def read(self):
        time.sleep(0.1)
        return self.bus.read_byte(self.i2c_address)


def menu():
    parser = argparse.ArgumentParser(description='Select I2C address and channel of TCA9548A I2C multiplexer')
    parser.add_argument('-a', '--address', metavar='ADDRESS', type=int,
                        help='I2C address of the multiplexer, only last two digits, (ex. enter "70" if 0x70)',
                        required=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-c', '--channel', metavar='CHANNEL', type=int,
                        help='Channel to be activated with the multiplexer',)
    group.add_argument('-r', '--read', action='store_true',
                        help='Only read multiplexer and return channel number',)

    args = parser.parse_args()

    i2c_address = int(str(args.address), 16)
    multiplexer = TCA9548A(i2c_address)
    if args.channel:
        multiplexer.setup(args.channel)
    read_response = multiplexer.read()
    print("TCA9548A I2C channel status: {} (channel {})".format(bin(read_response), read_response))

if __name__ == "__main__":
    menu()
