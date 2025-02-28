import base64
import logging
import secrets
import string

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding, serialization
from cryptography.hazmat.primitives.asymmetric import padding as rsa_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

_LOGGER = logging.getLogger(__name__)


class EncryptionUtils:
    PRIVATE_KEY = """MIICdwIBADANBgkqhkiG9w0BAQEFAASCAmEwggJdAgEAAoGBAOFizbd1fC5XNKJ89u0XNvPZNR/L
                         0h547iSWjOCuvvMu76ZSaS3/Tu2C1C+XmlnmBWTyY4ON+xECiNUXm/aWQ3P0g+wf60zjPbNzgL2Q
                         7njXJG6wka4KkbdQxUdS0TTpL256LnV1LsG855bsbJIJiQPbfUq6HbB5xH7sXdrmFu1DAgMBAAEC
                         gYEAoT2TGE1ncquWjyxBZup1uMvKkp25C23OSMSfslmxZ75LWjyY3HxK1eYDsKyPkwLZFxfFE6du
                         VwPuKiyCuk1ToPfnb4niTGzXPyC2PbO4SFrWL8n1YZ80M0bfTGI9dMCZvpmZJ41WYUsBaf2374lt
                         oEiDEHJp7MeXk/970xiKP1ECQQD65rLHk840q+FZS6kZVexJucPZj/YAII6klU1E20ctioe8Pi5m
                         WSPqclH27/t4FqdvP7tFqaavyXg+CEQpxmxLAkEA5fddDuzcjWgF9pl9fP7/baFMYjUS9z1Vc3gx
                         CnvAgCnv71wjDQhvsUc6sAiidsBGFDyud06RyyLcOlQchMb36QJBAIui/Xjpn+fciQxjeXcqRNk7
                         U+6vml+zvu+GUHyz9Uc5RBXWHYjEr6J5gXiHU1MgeIsH0zgQFT7cR9luTFFbp0UCQFIntfogCocG
                         E6NOoHMoUi5jQnuPRHBJXB69YJ/DKDlhQhN8EhWU3voxXTkITKop9J9EMnvy+MjecljwNaQFxQkC
                         QB9lz67iDe9Gj8NxSElVZxUm9EfbL1RPqTZPx/lADR06CPB8pP3Bl5/5/5RGzc+UTZ+wX5GWKvC7
                         zUJaROxQB+E=""".replace(" ", "")

    PUBLIC_KEY_PROD = """MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEApLbeSgOvnwLTWbhaBQWNnnHMtSDAi
                            Gz0PEDbrtd1tLYoO0hukW5PSa6eHykch0Hc6etiqEx1xziS+vNf+iOXds70I4htaYit6yRToZlQ
                            Mim3DQxaZX68nIHIZogur0zGv9U8j01v5l/rHRxyDdlVx3+JkBg6Cqx4U1PXEnAJriqcyg0B8Gm
                            V8Lnmfng+aJLRyq5MkhstYCRv9AsmWu8NpZDJ1ffbkaS02Z9/wpubXTiFP6DG3V2mDw2VvzEcHi
                            cchw49oXmTi92yui+kBgSYlNygssOAyU6H071AfmRUeH3+TsV5u5rg+bCiKyHemVmcKdd3hhZB+
                            HjA8o3On6rg5wIDAQAB""".replace(" ", "")

    PUBLIC_KEY_TEST = """MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQC1nAzH31arNBmYKvTlvKgkxI1MIr4HpfLbmM
                            XPIhd8D/cXB0dYY1ppUq4a/ezq41YShN88e0elyZgqdnFrkhiLpnKWa7jXtVRgXi9eS18PLO8ns
                            eHude9URaj7relK1AZ0xovKsbLKHd01PpmngLXZfnKA06J2ru/zH+cnpXdy8QIDAQAB""".replace(" ", "")

    def __init__(self) -> None:
        self.AES_PASW = self.get_aes_key()  # Get from previous implementation
        self.IV = self.get_iv()  # Get from previous implementation
        self._public_key = self.load_public_key()
        self._private_key = self.load_private_key()

    @staticmethod
    def load_private_key():
        """Load the private key from base64 encoded string"""
        try:
            private_key_bytes = base64.b64decode(EncryptionUtils.PRIVATE_KEY)
            return serialization.load_der_private_key(private_key_bytes, password=None, backend=default_backend())
        except Exception as e:
            raise Exception(f"Failed to load private key: {e!s}")

    @staticmethod
    def load_public_key(is_production: bool = True):
        """Load the public key from base64 encoded string

        Args:
            is_production (bool): If True, uses production key, else uses test key

        """
        try:
            key_string = EncryptionUtils.PUBLIC_KEY_PROD if is_production else EncryptionUtils.PUBLIC_KEY_TEST
            public_key_bytes = base64.b64decode(key_string)
            return serialization.load_der_public_key(public_key_bytes, backend=default_backend())
        except Exception as e:
            raise Exception(f"Failed to load public key: {e!s}")

    @staticmethod
    def encrypt(plaintext: str, key: str, iv: str) -> str:
        """Encrypt text using AES/CBC/PKCS5Padding

        Args:
            plaintext (str): Text to encrypt
            key (str): Encryption key
            iv (str): Initialization vector

        Returns:
            str: Base64 encoded encrypted string

        Raises:
            Exception: If encryption fails

        """
        try:
            # Convert strings to bytes
            plaintext_bytes = plaintext.encode("utf-8")
            key_bytes = key.encode("utf-8")
            iv_bytes = iv.encode("utf-8")

            # Create padder
            padder = padding.PKCS7(128).padder()
            padded_data = padder.update(plaintext_bytes) + padder.finalize()

            # Create cipher
            cipher = Cipher(algorithms.AES(key_bytes), modes.CBC(iv_bytes), backend=default_backend())

            # Encrypt
            encryptor = cipher.encryptor()
            encrypted_bytes = encryptor.update(padded_data) + encryptor.finalize()

            # Encode to base64
            return base64.b64encode(encrypted_bytes).decode("utf-8")

        except Exception as e:
            raise Exception(f"Encryption failed: {e!s}")

    def encryption_by_aes(self, text: str) -> str:
        """Encrypt text using AES with class-level key and IV

        Args:
            text (str): Text to encrypt

        Returns:
            str: Encrypted text or None if encryption fails

        """
        try:
            # Perform encryption
            encrypted = self.encrypt(text, self.AES_PASW, self.IV)

            return encrypted

        except Exception as e:
            _LOGGER.error(f"Encryption failed: {e!s}")
            return None

    def encrypt_by_public_key(self) -> str | None:
        """Encrypt data using RSA public key.

        Args:

        Returns:
            Optional[str]: Base64 encoded encrypted data or None if encryption fails

        """

        data = f"{self.AES_PASW},{self.IV}"

        if not self._public_key:
            _LOGGER.error("Public key not initialized")
            return None

        try:
            # Convert input string to bytes
            data_bytes = data.encode("utf-8")

            # Encrypt the data padding.PKCS7(128).padder()
            encrypted_bytes = self._public_key.encrypt(data_bytes, rsa_padding.PKCS1v15())

            # Convert to base64 string
            encrypted_str = base64.b64encode(encrypted_bytes).decode("utf-8")
            _LOGGER.debug("Data encrypted successfully")

            return encrypted_str

        except Exception as err:
            _LOGGER.error("Encryption failed: %s", str(err))
            return None

    @staticmethod
    def get_random_string(length: int) -> str:
        """Generate a random string of specified length using alphanumeric characters.

        Args:
            length (int): The desired length of the random string

        Returns:
            str: A random alphanumeric string of specified length

        Raises:
            ValueError: If length is less than 1

        """
        if length < 1:
            raise ValueError("Length must be positive")

        charset = string.ascii_letters + string.digits
        return "".join(secrets.choice(charset) for _ in range(length))

    @staticmethod
    def get_random_int(length: int) -> str:
        """Generate a random string of specified length containing only digits.

        Args:
            length (int): The desired length of the random number string

        Returns:
            str: A string of random digits of specified length

        Raises:
            ValueError: If length is less than 1

        """
        if length < 1:
            raise ValueError("Length must be positive")

        return "".join(secrets.choice(string.digits) for _ in range(length))

    @staticmethod
    def get_aes_key() -> str:
        """Generate a random AES key of 16 characters using alphanumeric characters.
        Matches Java implementation behavior.

        Returns:
            str: A 16-character random string for AES key

        """
        return EncryptionUtils.get_random_string(16)

    @staticmethod
    def get_iv() -> str:
        """Generate a random initialization vector of 16 digits.
        Matches Java implementation behavior.

        Returns:
            str: A 16-digit random string for initialization vector

        """
        return EncryptionUtils.get_random_int(16)
