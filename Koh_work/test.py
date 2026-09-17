import math

def gelu_reference(x):
    return 0.5 * x * (1 + math.erf(x / math.sqrt(2)))

print(gelu_reference(1.0))
