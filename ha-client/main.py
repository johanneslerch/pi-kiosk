import paho.mqtt.client as mqtt
import json
import time
import subprocess
import os
import psutil
import gpiod
from gpiozero import RGBLED

MQTT_BROKER = "homedroid"
MQTT_PORT = 1883

DEVICE_ID = "raspi-eg"
TOPIC_SENSORS = f"{DEVICE_ID}/sensors"
TOPIC_DISPLAY = f"{DEVICE_ID}/display"
TOPIC_DISPLAY_SET = f"{DEVICE_ID}/display/set"
TOPIC_BRIGHTNESS_STATE = f"{DEVICE_ID}/display/brightness"
TOPIC_BRIGHTNESS_STATE_SET = f"{DEVICE_ID}/display/brightness/set"
TOPIC_LED = f"{DEVICE_ID}/led"
TOPIC_LED_SET = f"{DEVICE_ID}/led/set"
TOPIC_LED_COLOR_STATE = f"{DEVICE_ID}/led/color"
TOPIC_LED_COLOR_STATE_SET = f"{DEVICE_ID}/led/color/set"

PIN_MOTION = 17



led = RGBLED(red=22, green=27, blue=23)
display_state = None
display_brightness = None

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("Connected to MQTT Broker!")
    else:
        print(f"Failed to connect to MQTT Broker, return code {reason_code}")

def on_message(client, userdata, msg):
    if msg.topic == TOPIC_DISPLAY_SET:
        if msg.payload.decode() == "ON":
            turn_display_on()
        elif msg.payload.decode() == "OFF":
            turn_display_off()
        else:
            raise RuntimeError("Invalid state for display: "+msg.payload.decode())
        publish_display_state(client)
    elif msg.topic == TOPIC_BRIGHTNESS_STATE_SET:
        set_display_brightness(int(msg.payload))
        publish_display_state(client)
    elif msg.topic == TOPIC_LED_SET:
        if msg.payload.decode() == "ON":
            turn_led_on(client)
        elif msg.payload.decode() == "OFF":
            turn_led_off(client)
        else:
            raise RuntimeError("Invalid state for display: "+msg.payload.decode())
    elif msg.topic == TOPIC_LED_COLOR_STATE_SET:
        set_led_color(client, msg.payload.decode())
    else:
        print(f"Received message for unhandled topic: {msg.topic}")

    

def register_device(client):
    payload = {
        "dev": {
            "ids": DEVICE_ID,
            "name": "RaspberryPi-EG"
        },
        "o": {
            "name": "Johannes Lerch"
        },
        "cmps": {
            "temperature_cpu": {
                "name": "CPU Temperature",
                "p": "sensor",
                "device_class": "temperature",
                "unit_of_measurement": "°C",
                "value_template":"{{ value_json.temperature_cpu}}",
                "unique_id":"rpi-eg-temp-cpu",
                "state_topic": TOPIC_SENSORS,
            },
            "display": {
                "name": "Display",
                "p": "light",
                "unique_id":"rpi-eg-brightness-display",
                "state_topic": TOPIC_DISPLAY,
                "command_topic": TOPIC_DISPLAY_SET,
                "brightness_state_topic": TOPIC_BRIGHTNESS_STATE,
                "brightness_command_topic": TOPIC_BRIGHTNESS_STATE_SET,
                "brightness_scale": get_max_display_brightness(),
                "payload_on": "ON",
                "payload_off": "OFF",
            },
            "motion": {
                "name": "Motion Sensor",
                "p": "binary_sensor",
                "unique_id": "rpi-eg-movement",
                "state_topic": TOPIC_SENSORS,
                "device_class": "motion",
                "payload_on": "ON",
                "payload_off": "OFF",
                "value_template":"{{ value_json.motion}}"
            },
            "led": {
                "name": "LED",
                "p": "light",
                "unique_id":"rpi-eg-led",
                "state_topic": TOPIC_LED,
                "command_topic": TOPIC_LED_SET,
                "rgb_state_topic": TOPIC_LED_COLOR_STATE,
                "rgb_command_topic": TOPIC_LED_COLOR_STATE_SET,
                "payload_on": "ON",
                "payload_off": "OFF",
                "rgb": True
            }
        }
    }
   
    client.publish(f"homeassistant/device/{DEVICE_ID}/config", json.dumps(payload), retain=True)
    print("Device and entities registered with Home Assistant.")

def publish_display_state(client):
    global display_state, display_brightness
    display_state = get_display_state()
    display_brightness = get_display_brightness()
    client.publish(TOPIC_DISPLAY, "ON" if display_state else "OFF")
    client.publish(TOPIC_BRIGHTNESS_STATE, display_brightness)

def publish_sensor_values(client, motion):
    payload = {
        "temperature_cpu": get_cpu_temperature(),
        "motion": "ON" if motion else "OFF"
    }
    client.publish(TOPIC_SENSORS, json.dumps(payload))

def get_cpu_temperature():
    with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
        temp = float(f.read()) / 1000.0 
    return round(temp, 2)

def terminate_process_tree(pid):
    parent = psutil.Process(pid)
    for child in parent.children(recursive=True):
        child.terminate()
    parent.terminate()

def turn_display_on():
    global turn_display_off_process
    if turn_display_off_process and turn_display_off_process.poll() is None:
        terminate_process_tree(turn_display_off_process.pid)

    env = os.environ.copy()
    env["WAYLAND_DISPLAY"] = "wayland-0"
    env["XDG_RUNTIME_DIR"] = "/run/user/1000"
    subprocess.run(["wlopm", "--on", "DSI-2"], env=env)

turn_display_off_process = None
def turn_display_off():
    global turn_display_off_process
    if turn_display_off_process and turn_display_off_process.poll() is None:
        terminate_process_tree(turn_display_off_process.pid)

    env = os.environ.copy()
    env["WAYLAND_DISPLAY"] = "wayland-0"
    env["XDG_RUNTIME_DIR"] = "/run/user/1000"
    turn_display_off_process = subprocess.Popen(["./turn-screen-off.sh"], env=env)

def get_display_state() -> bool:
    with open("/sys/class/backlight/11-0045/bl_power", "r") as f:
        return int(f.read().strip()) == 0

def get_max_display_brightness() -> int:
    with open("/sys/class/backlight/11-0045/max_brightness", "r") as f:
        return int(f.read().strip())

def get_display_brightness() -> int:
    with open("/sys/class/backlight/11-0045/actual_brightness", "r") as f:
        return int(f.read().strip())

def set_display_brightness(value: int):
    if value < 0 or value > get_max_display_brightness():
        raise RuntimeError("Display brightness out of range: "+value)
    with open("/sys/class/backlight/11-0045/brightness", "w") as file:
        file.write(str(value))

def turn_led_on(client):
    if not led.is_active:
        led.on()
    publish_led_values(client)

def turn_led_off(client):
    led.off()
    publish_led_values(client)

def set_led_color(client, color):
    led.color = tuple(float(color)/255 for color in color.split(","))
    publish_led_values(client)

def publish_led_values(client):
    client.publish(TOPIC_LED, "ON" if led.is_active else "OFF")
    client.publish(TOPIC_LED_COLOR_STATE, ",".join(str(round(color*255)) for color in led.color))

def main():
    chip = gpiod.Chip('gpiochip0')
    motion_line = chip.get_line(17)
    motion_line.request(consumer="gpio-reader", type=gpiod.LINE_REQ_EV_BOTH_EDGES )


    client = mqtt.Client(protocol=mqtt.MQTTv311, transport="tcp", callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(MQTT_BROKER, MQTT_PORT, 60)

    client.subscribe(TOPIC_DISPLAY_SET)
    client.subscribe(TOPIC_BRIGHTNESS_STATE_SET)
    client.subscribe(TOPIC_LED_SET)
    client.subscribe(TOPIC_LED_COLOR_STATE_SET)

    register_device(client)
    client.loop_start()

    publish_led_values(client)

    try:
        seconds = 0
        while True:
            motion_event = motion_line.event_read()
            if seconds == 60 or motion_event:
                publish_sensor_values(client, motion_event.type == gpiod.LineEvent.RISING_EDGE if motion_event else False)
                seconds = 0
            
            if display_state != get_display_state() or display_brightness != get_display_brightness():
                publish_display_state(client)
            
            time.sleep(1) 
            seconds += 1
    except KeyboardInterrupt:
        print("Stopping MQTT client.")
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()