import logging
from rpi_rf import RFDevice
from modules import cbpi
from modules.core.hardware import ActorBase, SensorPassive, SensorActive
from modules.core.props import Property
import time


@cbpi.actor
class Socket433MHz(ActorBase):
    protocol = Property.Select("Socket Protocol", configurable=True, description="Enter the Protocol that your socket is configured for. More protocols can be added in rpi_rf.")
    code_on = Property.Text("ON Code", configurable=True, description="Enter the code for turning the 433Hz socket on")
    code_off = Property.Text("OFF Code", configurable=True, description="Enter the code for turning the 433Hz socket off")
    pin =  Property.Text("GPIO PIN", configurable=True, description="Enter the code GPIO PIN for the rf transmitter")

    def on(self, power=100):
        logging.basicConfig(level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S',
                    format='%(asctime)-15s - [%(levelname)s] %(module)s: %(message)s',)
        rfdevice = RFDevice(int(self.pin))
        rfdevice.enable_tx()
        rfdevice.tx_code(int(self.code_on), None, None)
        rfdevice.cleanup()

    def off(self):
        logging.basicConfig(level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S',
                    format='%(asctime)-15s - [%(levelname)s] %(module)s: %(message)s',)
        rfdevice = RFDevice(int(self.pin))
        rfdevice.enable_tx()
        rfdevice.tx_code(int(self.code_off), None, None)
        rfdevice.cleanup()
