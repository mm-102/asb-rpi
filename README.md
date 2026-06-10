# Snake Charmer - Flute Controller

This repository contains the Python-based firmware for the "Flute" (mobile) module of the Snake Charmer project. Designed to run on a Raspberry Pi (e.g., Zero 2W), it reads spatial orientation from an MPU6050 IMU using its internal Digital Motion Processor (DMP) and registers button inputs.

The controller communicates securely with the ESP32 "Box" via CoAPS (DTLS with Pre-Shared Keys).

## Prerequisites & Installation

To run this project, you need specific system libraries for CoAPS communication and GPIO handling, alongside standard Python packages.

### 1. Install System Dependencies

The `gpiozero` library requires a backend daemon to handle GPIO pins efficiently. We use `pigpio` (usually installed by default on Raspbian). You also need the `libcoap` client with OpenSSL support for secure communication.

```bash
sudo apt update
sudo apt install pigpio libcoap3-bin openssl

```

Enable and start the `pigpio` daemon so it runs in the background (should be enabled by default on raspbian):

```bash
sudo systemctl enable pigpiod
sudo systemctl start pigpiod

```

### 2. Install Python Dependencies

It is recommended to use a virtual environment, or install globally if you are running a dedicated Pi.

```bash
pip install -r requirements.txt

```

### 3. Configuration

By default, the scripts point to the ESP32 Access Point IP and use hardcoded DTLS PSK credentials. If you changed these in the asb-box project, ensure you update them at the top of `asb-rpi.py` and `dbg.py`.

---

## Usage

### Running the Controller

To start the main game controller script manually:

```bash
python asb-rpi.py

```

**Debug Mode:**
If you want to verify that your IMU is working correctly, you can pass the `--debug` flag. This will print the real-time Roll, Pitch, and Yaw (Euler angles) directly to your terminal.

```bash
python asb-rpi.py --debug

```

### Running as a Background Service (systemd)

Since there is no automated install script, you can set the controller to run automatically on boot by creating a `systemd` service.

1. Create a new service file:

```bash
sudo nano /etc/systemd/system/asb-flute.service

```

2. Paste the following configuration (Ensure you replace `/home/pi/asb-rpi` with the actual path to this repository, and adjust the `User` if you aren't using the default `pi` user):

```ini
[Unit]
Description=Snake Charmer Flute Controller
After=network-online.target pigpiod.service
Wants=network-online.target pigpiod.service

[Service]
ExecStart=/usr/bin/python3 /home/pi/asb-rpi/asb-rpi.py
WorkingDirectory=/home/pi/asb-rpi
StandardOutput=inherit
StandardError=inherit
Restart=always
RestartSec=3
User=pi

[Install]
WantedBy=multi-user.target

```

3. Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable asb-flute.service
sudo systemctl start asb-flute.service

```

*(You can check the logs anytime using `journalctl -u asb-flute.service -f`)*

---

## Payload Data Formats

The communication between the Flute and the Box uses highly packed binary structs to minimize network overhead. The payloads are packed using Little-Endian byte order (`<`).

### 1. `EntryPayload` (Sent via POST `/entry`)

This structure represents a single recorded movement/button press.

* **Format string:** `<8sI3f` (24 bytes total)
* **Fields:**
* `name` (`8s`, 8 bytes): A string identifier for the instrument (e.g., "P1"). It is null-terminated and padded to exactly 8 bytes.
* `buttons` (`I`, 4 bytes): An unsigned 32-bit integer acting as a bitmask for the currently pressed buttons.
* `euler_angles` (`3f`, 12 bytes): Three 32-bit floats representing the IMU's spatial orientation (Roll, Pitch, Yaw).



### 2. `StatePayload` (Received from ESP32, or sent via POST `/set_state`)

This structure represents the current state of the game's logic machine.

* **Format string:** `<BB` (2 bytes total)
* **Fields:**
* `code` (`B`, 1 byte): Unsigned char representing the game mode (`0` = INPUT_WRITE_CODE, `1` = INPUT_CHECK_CODE).
* `progress` (`B`, 1 byte): Unsigned char representing the player's current step index in the sequence.



---

## Debugging Tool (`dbg.py`)

This repository includes a CLI debugging tool (`dbg.py`) that allows you to manually send specific CoAPS requests to any of the Box's endpoints. This is incredibly useful for testing the game logic without needing to physically wave the flute around.

**Usage Examples:**

Get the current game state:

```bash
python dbg.py state

```

Reset the player's progress back to 0:

```bash
python dbg.py reset

```

Trigger the save command manually:

```bash
python dbg.py save

```

Send a manual simulated entry (Requires exactly 5 arguments: `name`, `buttons_bitmask`, `roll`, `pitch`, `yaw`):

```bash
# Simulates pressing button bitmask 1, with Euler angles 1.5, -0.5, 3.14
python dbg.py entry Flute1 1 1.5 -0.5 3.14

```

Force the game into a specific state (Requires exactly 2 arguments: `mode`, `progress`):

```bash
# Force the box into Code Check Mode (1) with progress 0
python dbg.py set_state 1 0

```