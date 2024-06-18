import base64

class DatatypeConverter:
    encode_map = None

    @staticmethod
    def init_encode_map():
        if DatatypeConverter.encode_map is None:
            cArr = [0] * 64
            for i in range(26):
                cArr[i] = chr(i + 65)
            for i in range(26, 52):
                cArr[i] = chr(i - 26 + 97)
            for i in range(52, 62):
                cArr[i] = chr(i - 52 + 48)
            cArr[62] = '+'
            cArr[63] = '/'
            DatatypeConverter.encode_map = cArr
        return DatatypeConverter.encode_map

    @staticmethod
    def parseBase64Binary(s):
        return base64.b64decode(s)

    @staticmethod
    def printBase64Binary(bArr):
        return DatatypeConverter._printBase64Binary(bArr)

    @staticmethod
    def encode(i):
        return DatatypeConverter.encode_map[i & 63]

    @staticmethod
    def _printBase64Binary(bArr, i=0, i2=None):
        if i2 is None:
            i2 = len(bArr)
        cArr = [''] * (((i2 + 2) // 3) * 4)
        DatatypeConverter._printBase64Binary_core(bArr, i, i2, cArr, 0)
        return ''.join(cArr)

    @staticmethod
    def _printBase64Binary_core(bArr, i, i2, cArr, i3):
        DatatypeConverter.init_encode_map()  # Ensure encode_map is initialized
        while i2 >= 3:
            cArr[i3] = DatatypeConverter.encode(bArr[i] >> 2)
            cArr[i3 + 1] = DatatypeConverter.encode(((bArr[i] & 3) << 4) | ((bArr[i + 1] >> 4) & 15))
            cArr[i3 + 2] = DatatypeConverter.encode(((bArr[i + 1] & 15) << 2) | ((bArr[i + 2] >> 6) & 3))
            cArr[i3 + 3] = DatatypeConverter.encode(bArr[i + 2] & 63)
            i2 -= 3
            i += 3
            i3 += 4

        if i2 == 1:
            cArr[i3] = DatatypeConverter.encode(bArr[i] >> 2)
            cArr[i3 + 1] = DatatypeConverter.encode((bArr[i] & 3) << 4)
            cArr[i3 + 2] = '='
            cArr[i3 + 3] = '='

        if i2 == 2:
            cArr[i3] = DatatypeConverter.encode(bArr[i] >> 2)
            cArr[i3 + 1] = DatatypeConverter.encode(((bArr[i] & 3) << 4) | ((bArr[i + 1] >> 4) & 15))
            cArr[i3 + 2] = DatatypeConverter.encode((bArr[i + 1] & 15) << 2)
            cArr[i3 + 3] = '='

        return i3

# Usage Example:
# converter = DatatypeConverter()
# encoded = converter.printBase64Binary(b"Hello, World!")
# print(encoded)  # Output: "SGVsbG8sIFdvcmxkIQ=="
# decoded = converter.parseBase64Binary(encoded)
# print(decoded)  # Output: b'Hello, World!'
