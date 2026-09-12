import math

def softmax_reference(values):
    exp_values = [math.exp(x) for x in values]
    total = sum(exp_values)
    return [x / total for x in exp_values]

test = [2, 1, 0]

print(softmax_reference(test))


STEP = 0.25
EXP_MIN = -8.0
EXP_MAX = 0.0

exp_lut = []

x = EXP_MIN

while x <= EXP_MAX:
    exp_lut.append(math.exp(x))
    x += STEP


def exp_approx(x):
    x = max(EXP_MIN, min(EXP_MAX, x))

    index = round((x - EXP_MIN) / STEP)

    return exp_lut[index]


def softmax_approx(values):
    max_val = max(values)

    shifted = [x - max_val for x in values]

    exp_values = [exp_approx(x) for x in shifted]

    total = sum(exp_values)

    return [x / total for x in exp_values]


exact = softmax_reference(test)
approx = softmax_approx(test)

print("Exact:", exact)
print("Approx:", approx)

tests = [
    [2, 1, 0],
    [1.2, 0.3, -0.7],
    [3.1, 2.4, 1.8],
    [-1.0, -2.0, -3.0],
    [0.2, 0.1, 0.0]
]

errors = []

for test in tests:
    exact = softmax_reference(test)
    approx = softmax_approx(test)

    print("\nInput:", test)
    print("Exact:", exact)
    print("Approx:", approx)

    for e, a in zip(exact, approx):
        errors.append(abs(e - a))

print("\nMean error:", sum(errors) / len(errors))
print("Maximum error:", max(errors))
