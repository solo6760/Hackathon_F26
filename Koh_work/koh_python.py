import math

# Quantization settings
SCALE = 1 / 32
QMIN = -128
QMAX = 127


# Exact GeLU reference
def gelu_reference(x):
    return 0.5 * x * (1 + math.erf(x / math.sqrt(2)))


# Convert decimal -> INT8
def quantize(x):
    q = round(x / SCALE)
    return max(QMIN, min(QMAX, q))


# Convert INT8 -> decimal
def dequantize(q):
    return q * SCALE


# Build GeLU LUT
lut = []

for q_in in range(QMIN, QMAX + 1):

    x = dequantize(q_in)

    exact_output = gelu_reference(x)

    q_out = quantize(exact_output)

    lut.append(q_out)


# Verify LUT
errors = []

for q_in in range(QMIN, QMAX + 1):

    x = dequantize(q_in)

    exact_output = gelu_reference(x)

    q_out = lut[q_in - QMIN]

    lut_output = dequantize(q_out)

    error = abs(exact_output - lut_output)

    errors.append(error)


print("Number of LUT entries:", len(lut))
print("Mean absolute error:", sum(errors) / len(errors))
print("Maximum error:", max(errors))


# Test some values
for x in [-2, -1, 0, 1, 2]:

    q_in = quantize(x)

    q_out = lut[q_in - QMIN]

    exact = gelu_reference(x)
    approximate = dequantize(q_out)

    print(
        "x =", x,
        "exact =", exact,
        "LUT =", approximate
    )
