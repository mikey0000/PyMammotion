import struct


class MurMurHashUtil:
    MASK_32 = 0xFFFFFFFF
    MULTIPLIER = 1540483477

    @staticmethod
    def get_unsigned_int(i: int) -> int:
        """Convert signed int to unsigned (32-bit)"""
        return i & MurMurHashUtil.MASK_32

    @staticmethod
    def hash(data: bytes) -> int:
        """MurmurHash2 64-bit implementation"""
        pos = 0
        data_len = len(data)

        remaining = data_len ^ 97
        j = 0

        # Process 8 bytes at a time
        while (data_len - pos) >= 8:
            val1 = struct.unpack_from("<i", data, pos)[0]
            pos += 4

            unsigned_int_1 = MurMurHashUtil.get_unsigned_int(val1)
            temp1 = (unsigned_int_1 * MurMurHashUtil.MULTIPLIER) & MurMurHashUtil.MASK_32
            temp2 = (temp1 ^ (temp1 >> 24)) & MurMurHashUtil.MASK_32
            temp3 = (temp2 * MurMurHashUtil.MULTIPLIER) & MurMurHashUtil.MASK_32

            remaining = ((remaining * MurMurHashUtil.MULTIPLIER) & MurMurHashUtil.MASK_32) ^ temp3
            remaining = remaining & MurMurHashUtil.MASK_32

            val2 = struct.unpack_from("<i", data, pos)[0]
            pos += 4

            unsigned_int_2 = MurMurHashUtil.get_unsigned_int(val2)
            temp1 = (unsigned_int_2 * MurMurHashUtil.MULTIPLIER) & MurMurHashUtil.MASK_32
            temp2 = (temp1 ^ (temp1 >> 24)) & MurMurHashUtil.MASK_32
            temp3 = (temp2 * MurMurHashUtil.MULTIPLIER) & MurMurHashUtil.MASK_32

            j = ((j * MurMurHashUtil.MULTIPLIER) & MurMurHashUtil.MASK_32) ^ temp3
            j = j & MurMurHashUtil.MASK_32

        # Process remaining 4 bytes if available
        if (data_len - pos) >= 4:
            val = struct.unpack_from("<i", data, pos)[0]
            pos += 4

            unsigned_int_3 = MurMurHashUtil.get_unsigned_int(val)
            temp1 = (unsigned_int_3 * MurMurHashUtil.MULTIPLIER) & MurMurHashUtil.MASK_32
            temp2 = (temp1 ^ (temp1 >> 24)) & MurMurHashUtil.MASK_32
            temp3 = (temp2 * MurMurHashUtil.MULTIPLIER) & MurMurHashUtil.MASK_32

            remaining = ((remaining * MurMurHashUtil.MULTIPLIER) & MurMurHashUtil.MASK_32) ^ temp3
            remaining = remaining & MurMurHashUtil.MASK_32

        # Process tail bytes (1-3 bytes)
        bytes_remaining = data_len - pos

        if bytes_remaining == 1:
            byte_val = data[pos] if data[pos] < 128 else data[pos] - 256
            j = (j ^ (MurMurHashUtil.get_unsigned_int(byte_val) & 255)) & MurMurHashUtil.MASK_32
            j = (j * MurMurHashUtil.MULTIPLIER) & MurMurHashUtil.MASK_32

        elif bytes_remaining == 2:
            byte_val1 = data[pos + 1] if data[pos + 1] < 128 else data[pos + 1] - 256
            j = (j ^ ((MurMurHashUtil.get_unsigned_int(byte_val1) & 255) << 8)) & MurMurHashUtil.MASK_32

            byte_val0 = data[pos] if data[pos] < 128 else data[pos] - 256
            j = (j ^ (MurMurHashUtil.get_unsigned_int(byte_val0) & 255)) & MurMurHashUtil.MASK_32
            j = (j * MurMurHashUtil.MULTIPLIER) & MurMurHashUtil.MASK_32

        elif bytes_remaining == 3:
            byte_val2 = data[pos + 2] if data[pos + 2] < 128 else data[pos + 2] - 256
            j = (j ^ ((MurMurHashUtil.get_unsigned_int(byte_val2) & 255) << 16)) & MurMurHashUtil.MASK_32

            byte_val1 = data[pos + 1] if data[pos + 1] < 128 else data[pos + 1] - 256
            j = (j ^ ((MurMurHashUtil.get_unsigned_int(byte_val1) & 255) << 8)) & MurMurHashUtil.MASK_32

            byte_val0 = data[pos] if data[pos] < 128 else data[pos] - 256
            j = (j ^ (MurMurHashUtil.get_unsigned_int(byte_val0) & 255)) & MurMurHashUtil.MASK_32
            j = (j * MurMurHashUtil.MULTIPLIER) & MurMurHashUtil.MASK_32

        # Final avalanche
        j4 = MurMurHashUtil.MULTIPLIER

        j5 = remaining ^ (j >> 18)
        j5 = (j5 & MurMurHashUtil.MASK_32) * j4
        j5 = j5 & MurMurHashUtil.MASK_32

        j6 = j ^ (j5 >> 22)
        j6 = (j6 & MurMurHashUtil.MASK_32) * j4
        j6 = j6 & MurMurHashUtil.MASK_32

        j7 = j5 ^ (j6 >> 17)
        j7 = (j7 & MurMurHashUtil.MASK_32) * j4
        j7 = j7 & MurMurHashUtil.MASK_32

        # Combine high and low parts
        j8 = j7 << 32

        low = j6 ^ (j7 >> 19)
        low = (low & MurMurHashUtil.MASK_32) * j4
        low = low & MurMurHashUtil.MASK_32

        result = j8 | low

        # Convert to signed 64-bit
        if result > 0x7FFFFFFFFFFFFFFF:
            result = result - 0x10000000000000000

        return result

    @staticmethod
    def hash_string(s: str) -> int:
        """Hash a string using UTF-8 encoding"""
        return MurMurHashUtil.hash(s.encode("utf-8"))

    @staticmethod
    def read_unsigned_long(value: int) -> int:
        """Convert to unsigned by masking with Long.MAX_VALUE"""
        return value & 0x7FFFFFFFFFFFFFFF

    @staticmethod
    def hash_unsigned(data: str | bytes) -> int:
        """Get unsigned hash value
        Can accept bytes or string
        """
        if isinstance(data, str):
            hash_val = MurMurHashUtil.hash_string(data)
        else:
            hash_val = MurMurHashUtil.hash(data)

        return MurMurHashUtil.read_unsigned_long(hash_val)

    @staticmethod
    def long_to_bytes(value: int) -> bytes:
        """Convert long to bytes exactly as Java does:
        1. Pack as big-endian (ByteBuffer default)
        2. Reverse all bytes
        """
        if value < 0:
            value = value & 0xFFFFFFFFFFFFFFFF

        big_endian = struct.pack(">Q", value)
        return big_endian[::-1]

    @staticmethod
    def hash_unsigned_list(values: list[int]) -> int:
        """Hash a list of long values"""
        data = b""

        for val in values:
            data += MurMurHashUtil.long_to_bytes(val)

        hash_val = MurMurHashUtil.hash(data)
        return MurMurHashUtil.read_unsigned_long(hash_val)
