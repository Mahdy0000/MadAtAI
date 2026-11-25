// Sphinx-1 settings. Edit this file, then flash. This is the ONLY place you need to change.
#pragma once

// Your Wi-Fi (2.4 GHz only: the ESP32 cannot join 5 GHz networks).
// Tip: a phone hotspot works. Keep the laptop on the same network.
#define WIFI_SSID "YOUR_WIFI_NAME"
#define WIFI_PASS "YOUR_WIFI_PASSWORD"

// Motor driver (L298N). Keep the ENA and ENB jumper caps ON the L298N: speed is done by PWM on the IN pins.
#define PIN_IN1 13   // left motor  A
#define PIN_IN2 15   // left motor  B
#define PIN_IN3 14   // right motor A
#define PIN_IN4 2    // right motor B
// If the robot drives backwards or spins the wrong way, swap these (or swap the motor wires):
#define LEFT_INVERT  false
#define RIGHT_INVERT false

// Ultrasonic sensor (HC-SR04)
#define PIN_TRIG 12
#define PIN_ECHO 4   // put a 1k/2k voltage divider between the sensor ECHO and this pin (5 V -> 3.3 V)

// Safety
#define STOP_CM 15             // refuse to drive forward when something is closer than this
#define CMD_TIMEOUT_MS 600     // motors stop if no /drive command arrives for this long
#define MAX_PWM 255
