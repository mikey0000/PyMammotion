import struct


class MurMurHashUtil:
    @staticmethod
    def get_unsigned_int(i):
        return i & 0xFFFFFFFF

    @staticmethod
    def hash(byte_arr: bytes):
        # Create a bytearray view with little endian order
        position = 0
        remaining_bytes = len(byte_arr)

        # Initial values
        remaining = remaining_bytes ^ 97
        j = 0

        # Process 8 bytes at a time
        while remaining_bytes >= 8:
            multiplier = 1540483477

            # First 4 bytes
            unsigned_int = struct.unpack_from("<I", byte_arr, position)[0]
            position += 4
            unsigned_int = (MurMurHashUtil.get_unsigned_int(unsigned_int) * multiplier) & 0xFFFFFFFF
            remaining = (
                ((remaining * multiplier) & 0xFFFFFFFF)
                ^ (((unsigned_int ^ (unsigned_int >> 24)) & 0xFFFFFFFF) * multiplier) & 0xFFFFFFFF
            ) & 0xFFFFFFFF

            # Next 4 bytes
            unsigned_int2 = struct.unpack_from("<I", byte_arr, position)[0]
            position += 4
            unsigned_int2 = (MurMurHashUtil.get_unsigned_int(unsigned_int2) * multiplier) & 0xFFFFFFFF
            j = (
                ((j * multiplier) & 0xFFFFFFFF)
                ^ ((((unsigned_int2 ^ (unsigned_int2 >> 24)) & 0xFFFFFFFF) * multiplier) & 0xFFFFFFFF)
            ) & 0xFFFFFFFF

            remaining_bytes -= 8

        # Process remaining 4 bytes if available
        if remaining_bytes >= 4:
            multiplier = 1540483477
            unsigned_int3 = struct.unpack_from("<I", byte_arr, position)[0]
            position += 4
            unsigned_int3 = (MurMurHashUtil.get_unsigned_int(unsigned_int3) * multiplier) & 0xFFFFFFFF
            remaining = (
                ((remaining * multiplier) & 0xFFFFFFFF)
                ^ ((((unsigned_int3 ^ (unsigned_int3 >> 24)) & 0xFFFFFFFF) * multiplier) & 0xFFFFFFFF)
            ) & 0xFFFFFFFF
            remaining_bytes -= 4

        # Process final 1-3 bytes if available
        if remaining_bytes == 1:
            j = (
                ((j ^ (MurMurHashUtil.get_unsigned_int(byte_arr[position]) & 0xFF)) & 0xFFFFFFFF) * 1540483477
            ) & 0xFFFFFFFF
        elif remaining_bytes == 2:
            j = (j ^ ((MurMurHashUtil.get_unsigned_int(byte_arr[position + 1]) & 0xFF) << 8)) & 0xFFFFFFFF
            j = (
                ((j ^ (MurMurHashUtil.get_unsigned_int(byte_arr[position]) & 0xFF)) & 0xFFFFFFFF) * 1540483477
            ) & 0xFFFFFFFF
        elif remaining_bytes == 3:
            j = (j ^ ((MurMurHashUtil.get_unsigned_int(byte_arr[position + 2]) & 0xFF) << 16)) & 0xFFFFFFFF
            j = (j ^ ((MurMurHashUtil.get_unsigned_int(byte_arr[position + 1]) & 0xFF) << 8)) & 0xFFFFFFFF
            j = (
                ((j ^ (MurMurHashUtil.get_unsigned_int(byte_arr[position]) & 0xFF)) & 0xFFFFFFFF) * 1540483477
            ) & 0xFFFFFFFF

        # Final mixing
        multiplier = 1540483477
        j5 = (((remaining ^ (j >> 18)) & 0xFFFFFFFF) * multiplier) & 0xFFFFFFFF
        j6 = (((j ^ (j5 >> 22)) & 0xFFFFFFFF) * multiplier) & 0xFFFFFFFF
        j7 = (((j5 ^ (j6 >> 17)) & 0xFFFFFFFF) * multiplier) & 0xFFFFFFFF
        j8 = j7 << 32

        return j8 | ((((j6 ^ (j7 >> 19)) & 0xFFFFFFFF) * multiplier) & 0xFFFFFFFF)

    @staticmethod
    def hash_unsigned(s: str | bytes) -> None:
        if isinstance(s, str):
            return MurMurHashUtil.read_unsigned_long(MurMurHashUtil.hash(s.encode()))
        elif isinstance(s, bytes) or isinstance(s, bytearray):
            return MurMurHashUtil.read_unsigned_long(MurMurHashUtil.hash(s))
        return None

    @staticmethod
    def long2bytes(value: int) -> bytes:
        # Convert long to 8 bytes in little-endian order
        result = bytearray(8)
        for i in range(8):
            result[7 - i] = (value >> (i * 8)) & 0xFF
        return bytes(result)

    @staticmethod
    def read_unsigned_long(value: int) -> int:
        return value & 0x7FFFFFFFFFFFFFFF

    @staticmethod
    def hash_unsigned_list(long_list: list[int]):
        byte_arr = b""
        for i in range(len(long_list)):
            if i == 0:
                byte_arr = MurMurHashUtil.long2bytes(long_list[i])
            else:
                byte_arr += MurMurHashUtil.long2bytes(long_list[i])

        return MurMurHashUtil.read_unsigned_long(MurMurHashUtil.hash(byte_arr))

    @staticmethod
    def hash_string(s: str):
        return MurMurHashUtil.hash(s.encode())
