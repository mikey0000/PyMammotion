import base64


class DatatypeConverter:
    encode_map = None

    @staticmethod
    def init_encode_map():
        """Initialize the encode map for DatatypeConverter if it is not already
        initialized.

        This function initializes the encode map for DatatypeConverter by
        creating a list of 64 elements and populating it with characters for
        encoding. If the encode map is already initialized, it returns the
        existing encode map.

        Returns:
            list: The encode map for DatatypeConverter.

        """

        if DatatypeConverter.encode_map is None:
            cArr: list[str | int] = [0] * 64
            for num in range(26):
                cArr[num] = chr(num + 65)
            for num_2 in range(26, 52):
                cArr[num_2] = chr(num_2 - 26 + 97)
            for num_3 in range(52, 62):
                cArr[num_3] = chr(num_3 - 52 + 48)
            cArr[62] = "+"
            cArr[63] = "/"
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
    def _printBase64Binary(bArr: bytes, i: int = 0, i2=None):
        """Print the Base64 binary representation of a byte array.

        This function takes a byte array and optional start and end indices to
        print the Base64 binary representation.

        Args:
            bArr (list): A list of bytes to be converted to Base64 binary.
            i (int): The starting index of the byte array (default is 0).
            i2 (int): The ending index of the byte array (default is the length of bArr).

        Returns:
            str: The Base64 binary representation of the input byte array.

        """

        if i2 is None:
            i2 = len(bArr)
        cArr = [""] * (((i2 + 2) // 3) * 4)
        DatatypeConverter._printBase64Binary_core(bArr, i, i2, cArr, 0)
        return "".join(cArr)

    @staticmethod
    def _printBase64Binary_core(bArr: bytes, i, i2, cArr, i3):
        """Encode binary data into Base64 format.

        This function encodes binary data into Base64 format following the
        Base64 encoding algorithm.

        Args:
            bArr (list): List of binary data to be encoded.
            i (int): Starting index of the binary data to be encoded.
            i2 (int): Length of binary data to be encoded.
            cArr (list): List to store the encoded Base64 characters.
            i3 (int): Starting index in the cArr to store the encoded characters.

        Returns:
            int: The index in cArr where encoding ends.

        Note:
            This function assumes that DatatypeConverter has a method 'encode' and
            'init_encode_map' for encoding.

        """

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
            cArr[i3 + 2] = "="
            cArr[i3 + 3] = "="

        if i2 == 2:
            cArr[i3] = DatatypeConverter.encode(bArr[i] >> 2)
            cArr[i3 + 1] = DatatypeConverter.encode(((bArr[i] & 3) << 4) | ((bArr[i + 1] >> 4) & 15))
            cArr[i3 + 2] = DatatypeConverter.encode((bArr[i + 1] & 15) << 2)
            cArr[i3 + 3] = "="

        return i3


# Usage Example:
# converter = DatatypeConverter()
# encoded = converter.printBase64Binary(b"Hello, World!")
# print(encoded)  # Output: "SGVsbG8sIFdvcmxkIQ=="
# decoded = converter.parseBase64Binary(encoded)
# print(decoded)  # Output: b'Hello, World!'
