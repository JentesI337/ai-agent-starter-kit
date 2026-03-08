def fibonacci(n: int) -> int:
    """
    Berechnet die n-te Fibonacci-Zahl.
    
    Args:
        n (int): Die Position in der Fibonacci-Folge
    
    Returns:
        int: Die n-te Fibonacci-Zahl
    """
    if n <= 1:
        return n
    
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    
    return b

if __name__ == "__main__":
    # Teste die Funktion mit n=10
    result = fibonacci(10)
    print(f"fibonacci(10) = {result}")
    
    # Überprüfe Edge-Cases
    print(f"fibonacci(0) = {fibonacci(0)}")
    print(f"fibonacci(1) = {fibonacci(1)}")