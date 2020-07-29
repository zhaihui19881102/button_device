import requests
import json
import RPi.GPIO as GPIO
import time
from gpiozero import Button,LED
from signal import pause
from threading import Timer
import os

#led.blink()

#some constants that can be changed here

#LED BLINK it is used for the state of posting error,and the state of disconnected
LED_NOK_BLINK_ON=0.2 #the unit is second
LED_NOK_BLINK_OFF=0.2 #the unit is second
LED_NOK_TIMEOUT=10#if can not post success,the led will blink for x seconds

#when the button pressed.default the LED is OK ,the led will blink at this frequency
LED_OK_LED_ON=0.5#the unit is second
LED_OK_LED_OFF=0.5#the unit is second
LED_OK_TIMEOUT=2 # after the button pressed,no matter what the server,the led will blink 

#every key has a state
KEY_IDLE=0#idle state
KEY_OK_C=1#when pressed ,the default state to indicate that the button has been pressed
KEY_ERRROR_C=2#no answer from server,it will enter into the error state

#time_out related period setting
REGISTER_TIMEOUT=5
HEARTBEAT_TIMEOUT=5
TRYPOST_TIMEOUT=2
POST_PERIOD=5 # it includes register and hearbeat period

#GPIO configure
CONNECT_LED_IO=23

#press_cnt =0
#release_cnt =0
def get_server_info():
    config_file = open('/home/pi/button_interface/pi/button_py/button.conf')
    config_hash = {}
    for line in config_file:
        line_key=line.split("=")[0]
        line_value=line.split("=")[1].rstrip()
        config_hash[line_key]=line_value
        #print(config_hash)
    return config_hash['server_ip'],config_hash['server_port'],config_hash['device_id']

server_addr ,server_port,device_id=get_server_info()
url = 'http://'+server_addr + ":" + server_port + "/device/button" 

#url='http://192.168.3.2:8000/users/pi/'


print(url)
class Singleton(type):
    _instances ={}
    def __call__(cls,*args,**kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(
                Singleton,cls).__call__(*args,**kwargs)
        return cls._instances[cls]



#the class of single key(one key+ one button),now one button_device includes 4 keys
class KeyUnit(object):
    def __init__(self,gpioid,ledid,event):
        self.id = gpioid
        self.ledid=ledid
        self.button = Button(gpioid)
        self.led = LED(ledid)
        self.isTimeout = False
        self.button.when_pressed = self.try_post
        self.event=event
        self.posting = False
        self.postok = False
        self.pressed_timer=None
        self.pressed_ok_timer=None
        self.manager = KeyManager()
        self.ledon()
        self.state=KEY_IDLE
        #self.testTimer=Timer(0.5,self.getstate)
        #self.testTimer.start()
        
    def getstate(self):
        if(self.event=='red'):
            print(self.state)
            self.testTimer.run()
    def ledon(self):#sometimes it need to change
        self.led.on()
        
    def ledoff(self):#sometimes it need to change
        self.led.off()
        
    def ledblink(self,on_t,off_t):
        self.led.blink(off_t,on_t)
        
    def set_event_type(self,event):
        self.event = event
        
    def try_post(self):
        #print('You pressed button ',self.event)
        #self.ledblink(LED_BLINK_ON,LED_BLINK_OFF)
        #print('current state is {%s}',self.state)
        if(self.state==KEY_IDLE):
            #print('0 to 1')
            pass
        elif(self.state==KEY_OK_C):
            if self.pressed_ok_timer is not None or self.pressed_ok_timer.is_alive == True: 
                #print('cancel 1 to 1')
                self.pressed_ok_timer.cancel()
                
        elif(self.state==KEY_ERRROR_C):
            if self.pressed_timer is not None or self.pressed_timer.is_alive == True: 
                self.pressed_timer.cancel()
                #print('cancel 2 to 1')
            
        self.state=KEY_OK_C
        #self.ledon()
        self.ledblink(LED_OK_LED_ON,LED_OK_LED_OFF)
        
        self.pressed_ok_timer = Timer(LED_OK_TIMEOUT, self.server_ok_process)
        self.pressed_ok_timer.start()
        
        cmds = {
            'id':self.manager.id,
            'type':'button',
            'event':self.event
            }

        ret = self.manager.post_once(json.dumps(cmds),TRYPOST_TIMEOUT)
        if ret == True:
            self.postok = True
        else:
            self.postok = False
        
        

        

    def timeout(self):
        self.posting = False
        #after timeout the led should on,the connect led should blink.
        self.ledon()
        
    def server_idle_process(self):
        self.state=KEY_IDLE
        self.ledon()
        
    def server_ok_process(self):
        if self.postok:
            self.server_idle_process()
        else:
            self.server_nok_process()
    
    def server_nok_process(self):
        self.state=KEY_ERRROR_C
        self.ledblink(LED_NOK_BLINK_ON,LED_NOK_BLINK_OFF)
        self.pressed_timer = Timer(LED_NOK_TIMEOUT, self.server_idle_process)
        self.pressed_timer.start()
        
    def wait_for_response(self):
        pass


#the class of device . it includes 4 key objects and a connect led object
class KeyManager(metaclass=Singleton):
    def __init__(self,_id,connect_led_io):
        #connect_led.ledon:when powered on and connect ok///ledblink:when powered on and connect fail
        self.c_led=LED(connect_led_io)
        self.id=_id
        self.keys={}
        self.key_list = []
        self.events=[]
        self.register_ok = False
        self.mTimer = Timer(2,self.register)
        self.hb_timer = Timer(2,self.heart_beat)
            
    def post_once(self,json_strings,expired_time=5):
        try:
            r=requests.post(url,data=json_strings,headers={"Content-Type":"application/json"},timeout=expired_time)
            #print("return from server is {0}".format(r.content))
            
        except requests.exceptions.RequestException as e:
            #print(e)
            return False
        
        else:
            if r.content.decode('utf-8') == 'ok':
                return True
        return False
    
    def add_key(self,key):
        if key.event not in self.keys:
            self.keys[key.event]=key
            self.key_list.append(key)
            self.events.append(key.event)
        
    def register(self):
        if not self.keys:
            return False
        data={
            'id':self.id,
            'type':'button',
            'event':"register",
            'myevents':self.events
        }
        ret = self.post_once(json.dumps(data),REGISTER_TIMEOUT)
        if ret == True:
            print('register_ok')
            self.register_ok = True
        else:
            print('register_fail')
            self.register_ok = False
            self.mTimer = Timer(POST_PERIOD,self.register)
            self.mTimer.start()
            
    def run(self):
        self.mTimer.start()
        self.hb_timer.start()
        
    def heart_beat(self):
        data={
            'id':self.id,
            'type':'button',
            'event':"heartbeat",
        }
        ret = self.post_once(json.dumps(data),HEARTBEAT_TIMEOUT)
        if ret == True:
            print('hb ok')
            self.hbok = True
            self.c_led.on()
        else:
            print('hb fail')
            self.hbok = False
            self.c_led.blink(LED_NOK_BLINK_ON,LED_NOK_BLINK_OFF)
       
       # for key in self.key_list:
       #     if key.posting == False:
       #         if self.hbok == True:
       #             print('led on hb')
       #             key.ledon()
       #         else:
       #             key.ledoff()
                    
        self.hb_timer = Timer(POST_PERIOD,self.heart_beat)
        self.hb_timer.start()

        
manager = KeyManager(int(device_id),CONNECT_LED_IO)

keyA = KeyUnit(25,24,'red')
keyB = KeyUnit(7,8,'green')
#keyC = KeyUnit(12,1,'yellow')
keyC = KeyUnit(12,26,'yellow')#the GPIO 1 for yellow led changed to GPIO 26
keyD = KeyUnit(20,16,'blue')


manager.add_key(keyA)
manager.add_key(keyB)
manager.add_key(keyC)
manager.add_key(keyD)

manager.run()
print('ok')
pause()

#url='http://192.168.1.2:5002/device/button'
#data={'id':12345,'type':'button','event':'register','myevents':['pi_red','pi_green']}

#cmdstr=json.dumps(data)
#print("Now posting {0}".format(cmdstr))
#r=requests.post(url,data=cmdstr,timeout=5)

#print(r.content)
