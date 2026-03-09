def is_palindrome(s):
    # Entferne Leerzeichen und konvertiere zu Kleinbuchstaben
    cleaned = ''.join(s.split()).lower()
    # Prüfe, ob der bereinigte String gleich seiner Umkehrung ist
    return cleaned == cleaned[::-1]
