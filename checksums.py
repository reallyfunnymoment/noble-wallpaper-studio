from pathlib import Path
import struct, binascii, zlib

def table32():
    table=[]
    for value in range(256):
        crc=value<<24
        for _ in range(8):
            crc=((crc<<1) ^ (0x04c11db7 if crc&0x80000000 else 0))&0xffffffff
        table.append(crc)
    return table

TABLE=table32()

def crc32_nonref(data, initial=0xffffffff):
    crc=initial
    for value in data:
        crc=((crc<<8)&0xffffffff)^TABLE[(crc>>24)^value]
    return crc

def reverse_words(data):
    result=bytearray(len(data))
    for i in range(4):result[i::4]=data[3-i::4]
    return result

if __name__=='__main__':
    data=(Path(__file__).parent/'resource_10_901_1033.bin').read_bytes()
    for offset in [0, 20, 56]:
        block=data[offset:-4]
        for order, block2 in [('bytes',block),('words',reverse_words(block))]:
            for init in [0,0xffffffff]:
                print(offset,order,hex(init),hex(crc32_nonref(block2,init)),flush=True)
