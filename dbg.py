import asyncio
import struct
import os
import argparse
from dataclasses import dataclass

ESP32_IP = "192.168.4.1"
USERNAME = 'asb-box'
PASSWORD = 'bajojajo'

INPUT_WRITE_CODE = 0
INPUT_CHECK_CODE = 1

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
        # Fixed: Unpacked the tuple for formatting
        angles = self.euler_angles
        return f"Entry: [name: {self.name}, buttons: {self.buttons}, angles: ({angles[0]:.2f}, {angles[1]:.2f}, {angles[2]:.2f})]"

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
    
    # Write payload to temp file if we have one
    if payload_bytes:
        with open(req_file, 'wb') as f:
            f.write(payload_bytes)
            
    cmd = [
        'coap-client-openssl', 
        '-m', method.lower(), 
        '-u', USERNAME, 
        '-k', PASSWORD,
        '-o', res_file, # Tell libcoap to dump the response payload here
    ]
    
    if payload_bytes:
        cmd.extend(['-f', req_file]) # Tell libcoap to send this file
        
    cmd.append(f'coaps://{ESP32_IP}/{endpoint}')
    
    process = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    await process.communicate()
    
    # Read the binary response
    response_data = b""
    if os.path.exists(res_file):
        with open(res_file, 'rb') as f:
            response_data = f.read()
            
    # Cleanup temp files
    if os.path.exists(req_file): os.remove(req_file)
    if os.path.exists(res_file): os.remove(res_file)
        
    return response_data


async def req_reset():
    return await coap_request('GET', 'reset')

async def req_state():
    res = await coap_request('GET', 'state')
    if res: return StatePayload.parse(res)
    return None

async def req_entry(payload: EntryPayload):
    res = await coap_request('POST', 'entry', payload.packed)
    if res: return StatePayload.parse(res)
    return None

async def req_set_state(payload: StatePayload):
    res = await coap_request('POST', 'set_state', payload.packed)
    if res: return StatePayload.parse(res)
    return None

async def req_save():
    return await coap_request('POST', 'save')


# --- CLI Parsing Logic ---

def parse_entry_payload(payload_args) -> EntryPayload:
    if len(payload_args) != 5:
        raise ValueError("Endpoint 'entry' requires exactly 5 payload arguments: <name> <buttons> <angle1> <angle2> <angle3>\nExample: entry Flute1 0 1.5 -0.5 3.14")
    
    # name encoded and strictly null-terminated if under 8 chars, struct pack <8s handles truncation/padding automatically
    name = payload_args[0].encode('utf-8')
    buttons = int(payload_args[1], 0) # 0 allows auto-detecting base 10, hex (0x...), bin (0b...)
    euler_angles = (float(payload_args[2]), float(payload_args[3]), float(payload_args[4]))
    
    return EntryPayload(name, buttons, euler_angles)

def parse_state_payload(payload_args) -> StatePayload:
    if len(payload_args) != 2:
        raise ValueError("Endpoint 'set_state' requires exactly 2 payload arguments: <code> <progress>\nExample: set_state 0 0")
    
    code = int(payload_args[0], 0)
    progress = int(payload_args[1], 0)
    
    return StatePayload(code, progress)


async def main():
    parser = argparse.ArgumentParser(description="CoAP Client for ESP32")
    parser.add_argument(
        'endpoint', 
        choices=['reset', 'state', 'entry', 'set_state', 'save'],
        help="The CoAP endpoint to trigger."
    )
    parser.add_argument(
        'payload', 
        nargs='*', # Accepts 0 or more trailing arguments as a list
        help="Optional payload parameters based on endpoint type."
    )
    
    args = parser.parse_args()
    
    try:
        # Determine the action and parse the payload dynamically
        if args.endpoint == 'reset':
            print(f"Sending GET request to /reset...")
            res = await req_reset()
            print(f"Response: {res}")
            
        elif args.endpoint == 'state':
            print(f"Sending GET request to /state...")
            res = await req_state()
            print(f"Response: {res}")
            
        elif args.endpoint == 'save':
            print(f"Sending POST request to /save...")
            res = await req_save()
            print(f"Response: {res}")
            
        elif args.endpoint == 'entry':
            payload = parse_entry_payload(args.payload)
            print(f"Sending POST request to /entry with {payload}...")
            res = await req_entry(payload)
            print(f"Response: {res}")
            
        elif args.endpoint == 'set_state':
            payload = parse_state_payload(args.payload)
            print(f"Sending POST request to /set_state with {payload}...")
            res = await req_set_state(payload)
            print(f"Response: {res}")
            
    except ValueError as e:
        print(f"Payload Error: {e}")
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())