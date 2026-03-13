import math

def pythagorean_triplet(n):
    """
    Find a Pythagorean triplet (a, b, c) where a^2 + b^2 = c^2 and a * b * c = n.
    
    Args:
        n (int): The product of the triplet
        
    Returns:
        list: A Pythagorean triplet [a, b, c] in increasing order, or None if not found
    """
    # We need to find a, b, c such that:
    # 1. a^2 + b^2 = c^2
    # 2. a * b * c = n
    # 3. a < b < c
    
    # Upper bound for a: since a < b < c, we have a^3 < a*b*c = n, so a < n^(1/3)
    max_a = int(n**(1/3)) + 1
    
    for a in range(1, max_a + 1):
        # Skip if a doesn't divide n
        if n % a != 0:
            continue
            
        # Now we have a, so b * c = n / a
        bc = n // a
        
        # Upper bound for b: since b < c, we have b^2 < b*c = bc, so b < sqrt(bc)
        max_b = int(math.sqrt(bc)) + 1
        
        for b in range(a + 1, max_b + 1):
            # Skip if b doesn't divide bc
            if bc % b != 0:
                continue
                
            c = bc // b
            
            # Check if it forms a valid Pythagorean triplet
            # That is, a^2 + b^2 = c^2
            if a*a + b*b == c*c:
                return [a, b, c]
    
    # No triplet found
    return None

# Example usage:
if __name__ == "__main__":
    print(pythagorean_triplet(60))    # [3, 4, 5]
    print(pythagorean_triplet(780))   # [5, 12, 13]
    print(pythagorean_triplet(2040))  # [8, 15, 17]