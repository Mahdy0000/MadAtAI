# Wiring

Two power rails: **motors** on their own battery pack, **logic** (ESP32-CAM + sensor) on a clean 5 V supply. **All grounds must be connected together.**

## Pin map

| ESP32-CAM pin | Goes to | Notes |
| --- | --- | --- |
| GPIO 13 | L298N IN1 | left motor |
| GPIO 15 | L298N IN2 | left motor |
| GPIO 14 | L298N IN3 | right motor |
| GPIO 2  | L298N IN4 | right motor |
| GPIO 12 | HC-SR04 TRIG | |
| GPIO 4  | HC-SR04 ECHO, **through a voltage divider** | the sensor outputs 5 V, the ESP32 pins are 3.3 V |
| 5V      | 5 V supply + | at least 500 mA available |
| GND     | common ground | |

L298N: keep the two **ENA / ENB jumper caps on**. Speed is controlled by PWM on the IN pins, so the EN pins are not connected to the ESP32.

## Power

```
 [2x 18650 pack, 7.4 V] --+--> L298N 12V terminal (motor power)
                          |
                          +--> buck converter (set to 5.0 V) --> ESP32-CAM 5V pin
                                                             --> HC-SR04 VCC
 All grounds joined:  battery -, L298N GND, buck GND, ESP32-CAM GND, HC-SR04 GND
```

Do not power the ESP32-CAM from the L298N's 5 V pin if you can avoid it: motor noise makes the board reboot. Use the buck converter.

## Echo voltage divider

```
 HC-SR04 ECHO ---[ 1k ]---+---> ESP32 GPIO 4
                          |
                        [ 2k ]
                          |
                         GND
```

## Motors

```
 L298N OUT1/OUT2 -> left motor      L298N OUT3/OUT4 -> right motor
```

If a wheel spins the wrong way, swap its two motor wires or flip `LEFT_INVERT` / `RIGHT_INVERT` in `firmware/sphinx1_cam/config.h`.

## Mounting

Camera and ultrasonic sensor both face forward, sensor centered under or beside the camera, a few cm above the floor.
