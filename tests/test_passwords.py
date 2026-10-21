from utils.passwords import hash_password, verify_password


def test_hash_and_verify_password_longer_than_bcrypt_limit():
    password = "a" * 100
    encoded_hash = hash_password(password)

    assert encoded_hash.startswith("$pbkdf2-sha256$")
    assert verify_password(password, encoded_hash) == (True, False)
    assert verify_password(password + "different", encoded_hash) == (False, False)


def test_hash_and_verify_password_with_multibyte_utf8():
    password = "ñ" * 40  # 80 UTF-8 bytes
    encoded_hash = hash_password(password)

    assert verify_password(password, encoded_hash) == (True, False)
