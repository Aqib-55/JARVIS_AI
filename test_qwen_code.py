import math


def is_prime(n: int) -> bool:
    if isinstance(n, bool) or not isinstance(n, int):
        raise TypeError("Input must be an integer")

    if n < 2:
        return False

    if n == 2:
        return True

    if n % 2 == 0:
        return False

    for i in range(3, math.isqrt(n) + 1, 2):
        if n % i == 0:
            return False

    return True


tests = [
    (7, True),
    (4, False),
    (1, False),
    (-5, False),
    (2, True),
    (49, False),
    (97, True),
]

for number, expected in tests:
    result = is_prime(number)
    assert result == expected, f"Failed: {number}"

# Verify invalid inputs raise TypeError
for invalid_input in [3.5, "hello", True]:
    try:
        is_prime(invalid_input)
        assert False, f"Expected TypeError for {invalid_input}"
    except TypeError:
        pass

print(f"All {len(tests)} tests passed.")
