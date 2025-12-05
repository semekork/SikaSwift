import bcrypt

def hash_pin(pin: str) -> str:
    """
    Turns "1234" into a secure hash like "$2b$12$..."
    """
    # bcrypt requires bytes, not strings
    pin_bytes = pin.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pin_bytes, salt)
    return hashed.decode('utf-8') # Return as string for database

def verify_pin(plain_pin: str, hashed_pin: str) -> bool:
    """
    Checks if "1234" matches the stored hash.
    """
    if not hashed_pin:
        return False
    
    pin_bytes = plain_pin.encode('utf-8')
    hashed_bytes = hashed_pin.encode('utf-8')
    
    return bcrypt.checkpw(pin_bytes, hashed_bytes)