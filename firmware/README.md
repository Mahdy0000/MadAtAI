# Firmware: ESP32-CAM (AI-Thinker)

Status: written to the board's datasheet pinout and the esp32 Arduino core examples, **not yet tested on real hardware by the authors**. Use the bring-up checklist at the bottom.

## What you need

- AI-Thinker ESP32-CAM (with the OV2640 camera)
- A way to flash it: an **ESP32-CAM-MB** USB base board (easiest), or an FTDI USB-serial adapter plus 2 jumper wires
- Arduino IDE 2.x
- A 2.4 GHz Wi-Fi network (a phone hotspot works)

## Flash it, step by step

1. **Install the Arduino IDE** from arduino.cc.
2. **Add the ESP32 board package.** File > Preferences > "Additional boards manager URLs", paste:
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`
   Then Tools > Board > Boards Manager, search `esp32`, install **"esp32 by Espressif Systems"**, version **3.0.x or newer** (the code uses `analogWrite`, which needs core 3.x).
3. **Set your Wi-Fi.** Open `firmware/sphinx1_cam/sphinx1_cam.ino` (the folder must be named `sphinx1_cam`). Open the `config.h` tab and edit:
   ```c
   #define WIFI_SSID "YOUR_WIFI_NAME"
   #define WIFI_PASS "YOUR_WIFI_PASSWORD"
   ```
4. **Select the board.** Tools menu:
   - Board: **AI Thinker ESP32-CAM**
   - Port: the USB serial port that appears when you plug the board in
   - Partition Scheme: **Huge APP (3MB No OTA/1MB SPIFFS)**
   - Upload Speed: 115200
5. **Enter flash mode.**
   - With an **ESP32-CAM-MB** base: nothing to do, just plug in USB.
   - With an **FTDI adapter**: wire FTDI 5V to 5V, GND to GND, FTDI TX to **U0R**, FTDI RX to **U0T**, and connect **IO0 to GND**. Then press the RST button on the ESP32-CAM.
6. **Click Upload.** Wait for "Hard resetting via RTS pin".
7. **Leave flash mode** (FTDI only): remove the IO0-GND wire and press RST.
8. **Read the address.** Tools > Serial Monitor, baud **115200**, press RST. You should see `camera ok` and then `READY. Robot address: http://192.168.x.x`. Write that address down.
9. **Check from the laptop** (same Wi-Fi). Open `http://<robot address>/stream` in a browser: you should see live video. `http://<robot address>/status` should show JSON with `distance_cm`.

## Wiring

See [../docs/WIRING.md](../docs/WIRING.md) for the full diagram and the pin map.

## FIRST: safety test (do this before anything else, wheels off the ground)

The robot must stop by itself if the laptop or Wi-Fi disappears. Test it:

1. Lift the robot so the wheels spin freely. Power it and wait for `READY` in the Serial Monitor.
2. On the laptop, in a browser, open `http://<robot address>/drive?l=150&r=150`. Wheels spin, then stop after about half a second. This is the 600 ms command timeout working.
3. Now the real test: start the agents against the robot (`python -m sphinx1 --robot http --url http://<robot address> ...`) so the wheels are being driven continuously, then **turn off the laptop's Wi-Fi (or unplug the router, or close the laptop lid)** while the wheels are turning.
4. The wheels must stop within about 1 second and stay stopped. If they keep turning, cut the motor battery immediately and do not run the robot on the floor until this is fixed (check `CMD_TIMEOUT_MS` in `config.h`).
5. Turn Wi-Fi back on. The robot reconnects by itself and still does nothing until it gets a new command.

Always keep a hand on the motor battery switch during the first floor runs.

## Bring-up checklist (do these in order, wheels off the ground first)

1. Serial Monitor shows `camera ok` and an IP address.
2. `/stream` shows video. If not: check the camera ribbon cable, and power the board from a solid 5 V source (USB from a laptop port is often too weak once Wi-Fi starts; brownouts show as random reboots).
3. `/distance` returns a number that changes when you move your hand in front of the sensor. `-1` means no echo.
4. With the robot lifted, open `http://<robot address>/drive?l=150&r=150`. Both wheels should spin forward for about half a second and then stop on their own. If a wheel goes the wrong way, flip `LEFT_INVERT` or `RIGHT_INVERT` in `config.h`.
5. `http://<robot address>/drive?l=150&r=-150` should spin the robot to the right (left wheel forward, right wheel back).
6. Put your hand 10 cm in front of the sensor and call `/drive?l=150&r=150`: it must answer `blocked`.
7. Then run the laptop agents against it (see the top-level README).

## API

| Endpoint | What |
| --- | --- |
| `/status` | JSON: ip, rssi, uptime_s, distance_cm |
| `/jpg` | one JPEG frame |
| `/stream` | MJPEG stream |
| `/distance` | forward distance in cm (plain text, `-1` = no echo) |
| `/drive?l=<-255..255>&r=<-255..255>` | set motor speeds; stops by itself after 600 ms |
| `/stop` | stop |

## Known limits

- Pins 2, 4, 12, 13, 14, 15 are shared with the microSD slot on this board, so the SD card cannot be used.
- GPIO 12 must be low at boot or the chip fails to start. The HC-SR04 TRIG input does not drive it high, so this is fine as wired.
- Very low PWM values may not turn the motors at all. The agents never command below 60.
