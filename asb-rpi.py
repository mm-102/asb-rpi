import asyncio
import struct
import os
import time
import argparse
import threading
from dataclasses import dataclass
from gpiozero import Button
from mpu6050 import MPU6050

ESP32_IP = "192.168.4.1"
USERNAME = 'asb-box'
PASSWORD = 'bajojajo'

NAME = "P1"

INPUT_WRITE_CODE = 0
INPUT_CHECK_CODE = 1

# gpios
BTN_PINS = [27, 22, 23, 24, 25]
SEND_BTN_PIN = 4
data_buttons = [Button(pin, pull_up=True) for pin in BTN_PINS]
send_button = Button(SEND_BTN_PIN, pull_up=True)

# imu setup
i2c_bus = 1
device_address = 0x68
freq_divider = 0x04

mpu = MPU6050(i2c_bus, device_address, freq_divider)
mpu.dmp_initialize()
mpu.set_DMP_enabled(True)
packet_size = mpu.DMP_get_FIFO_packet_size()

latest_euler = (0.0, 0.0, 0.0)

@dataclass(frozen=True)
class EntryPayload:
    name: bytes
    buttons: int
    euler_angles: tuple[float, float, float]

    @property
    def packed(self) -> bytes:
        return struct.pack(
            '<8sI3f', 
            self.name, 
            self.buttons,
            self.euler_angles[0],
            self.euler_angles[1],
            self.euler_angles[2]
        )
    
    def __repr__(self) -> str:
        name_str = self.name.decode('utf-8', 'ignore').strip(chr(0))
        return f"Entry: [name: {name_str}, buttons: {bin(self.buttons)}, angles: ({self.euler_angles[0]:.2f}, {self.euler_angles[1]:.2f}, {self.euler_angles[2]:.2f})]"

@dataclass(frozen=True)
class StatePayload:
    code: int
    progress: int

    @classmethod
    def parse(cls, raw_bytes: bytes):
        if len(raw_bytes) != 2:
            print(f"Error: Expected 2 bytes for state, got {len(raw_bytes)}")
            return None
        code, progress = struct.unpack('<BB', raw_bytes)
        return cls(code, progress)
    
    @property
    def packed(self) -> bytes:
        return struct.pack('<BB', self.code, self.progress)
    
    def __repr__(self) -> str:
        return f"State: [code: {self.code}, progress: {self.progress}]"


async def coap_request(method, endpoint, payload_bytes=None):
    req_file = "req.bin"
    res_file = "res.bin"
    
    if payload_bytes:
        with open(req_file, 'wb') as f:
            f.write(payload_bytes)
            
    cmd = [
        'coap-client-openssl', 
        '-m', method.lower(), 
        '-u', USERNAME, 
        '-k', PASSWORD,
        '-o', res_file,
    ]
    
    if payload_bytes:
        cmd.extend(['-f', req_file])
        
    cmd.append(f'coaps://{ESP32_IP}/{endpoint}')
    
    process = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    await process.communicate()
    
    response_data = b""
    if os.path.exists(res_file):
        with open(res_file, 'rb') as f:
            response_data = f.read()
            
    if os.path.exists(req_file): os.remove(req_file)
    if os.path.exists(res_file): os.remove(res_file)
        
    return response_data

async def req_entry(payload: EntryPayload):
    return await coap_request('POST', 'entry', payload.packed)


def sensor_worker(debug_mode: bool):
    global latest_euler
    
    while True:
        try:
            packets_read = 0
            while mpu.isreadyFIFO(packet_size):
                FIFO_buffer = mpu.get_FIFO_bytes(packet_size)
                q = mpu.DMP_get_quaternion_int16(FIFO_buffer)
                roll_pitch_yaw = mpu.DMP_get_euler_roll_pitch_yaw(q)
                latest_euler = (roll_pitch_yaw.x, roll_pitch_yaw.y, roll_pitch_yaw.z)
                
                packets_read += 1
                if packets_read > 50:
                    break
            
            if debug_mode and packets_read > 0:
                print(f"\r\033[K[DEBUG] Roll: {latest_euler[0]:>7.2f} | Pitch: {latest_euler[1]:>7.2f} | Yaw: {latest_euler[2]:>7.2f}", end='', flush=True)
            
            time.sleep(0.001) 
            
        except Exception as e:
            if debug_mode:
                print(f"\n[DEBUG] Sensor Error: {e} -> Resetting FIFO")
            mpu.reset_FIFO()
            time.sleep(0.05)


async def controller_task(debug_mode: bool):
    global latest_euler
    entry_counter = 1
    
    while True:
        if send_button.is_pressed:
            if debug_mode:
                print()
            
            button_state = 0
            for i, btn in enumerate(data_buttons):
                if btn.is_pressed:
                    button_state |= (1 << i)
            
            name_bytes = f"{NAME}\0".encode('utf-8')[:8]
            payload = EntryPayload(name_bytes, button_state, latest_euler)
            
            print(f"Sending -> {payload}")
            
            res_bytes = await req_entry(payload)
            if res_bytes:
                print(f"Response <- {StatePayload.parse(res_bytes)}")
            else:
                print("Response <- Timeout/No Data")
            
            entry_counter += 1
            
            await asyncio.sleep(0.5)
            
        await asyncio.sleep(0.02)


async def main():
    parser = argparse.ArgumentParser(description="Raspberry Pi Game Controller")
    parser.add_argument('--debug', action='store_true', help="Enable live Euler angle streaming to the terminal.")
    args = parser.parse_args()

    print("\nGame Controller Ready!")
    print(f"Data Buttons: GPIO {BTN_PINS}")
    print(f"Send Button:  GPIO {SEND_BTN_PIN}")
    if args.debug:
        print("Debug mode: ENABLED\n")

    sensor_thread = threading.Thread(target=sensor_worker, args=(args.debug,), daemon=True)
    sensor_thread.start()
    
    await controller_task(args.debug)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting gracefully...")