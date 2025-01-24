import paho.mqtt.client as mqtt
import json
import time
import subprocess
import os

MQTT_BROKER = "homedroid"
MQTT_PORT = 1883

DEVICE_ID = "raspi-eg"
TOPIC_SENSORS = f"{DEVICE_ID}/sensors"
TOPIC_DISPLAY = f"{DEVICE_ID}/display"
TOPIC_DISPLAY_SET = f"{DEVICE_ID}/display/set"
TOPIC_BRIGHTNESS_STATE = f"{DEVICE_ID}/display/brightness"
TOPIC_BRIGHTNESS_STATE_SET = f"{DEVICE_ID}/display/brightness/set"


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
    elif msg.topic == TOPIC_BRIGHTNESS_STATE_SET:
        set_display_brightness(int(msg.payload))
    else:
        print(f"Received message for unhandled topic: {msg.topic}")

    publish_display_state(client)

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

def publish_sensor_values(client):
    payload = {
        "temperature_cpu": get_cpu_temperature()
    }
    client.publish(TOPIC_SENSORS, json.dumps(payload))

def get_cpu_temperature():
    with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
        temp = float(f.read()) / 1000.0 
    return round(temp, 2)

def turn_display_on():
    env = os.environ.copy()
    env["WAYLAND_DISPLAY"] = "wayland-0"
    env["XDG_RUNTIME_DIR"] = "/run/user/1000"
    subprocess.run(["wlopm", "--on", "DSI-2"], env=env)

def turn_display_off():
    env = os.environ.copy()
    env["WAYLAND_DISPLAY"] = "wayland-0"
    env["XDG_RUNTIME_DIR"] = "/run/user/1000"
    subprocess.run(["wlopm", "--off", "DSI-2"], env=env)

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

def main():
    client = mqtt.Client(protocol=mqtt.MQTTv311, transport="tcp", callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(MQTT_BROKER, MQTT_PORT, 60)

    client.subscribe(TOPIC_DISPLAY_SET)
    client.subscribe(TOPIC_BRIGHTNESS_STATE_SET)

    register_device(client)
    client.loop_start()

    try:
        seconds = 0
        while True:
            if seconds == 60:
                publish_sensor_values(client)
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