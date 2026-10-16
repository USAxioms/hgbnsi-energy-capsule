"""Integer-only deterministic random numbers (splitmix64 seeding, xorshift64* stream).
Replaces Python's random module, whose random() and gauss() return floats."""
M64 = (1 << 64) - 1

class Rng:
    def __init__(self, seed):
        x = (seed + 0x9E3779B97F4A7C15) & M64
        x = ((x ^ (x >> 30)) * 0xBF58476D1CE4E5B9) & M64
        x = ((x ^ (x >> 27)) * 0x94D049BB133111EB) & M64
        self.s = (x ^ (x >> 31)) | 1

    def next64(self):
        s = self.s
        s ^= s >> 12; s ^= (s << 25) & M64; s ^= s >> 27
        self.s = s
        return (s * 0x2545F4914F6CDD1D) & M64

    def below(self, n):
        """Uniform integer in [0, n), exactly (rejection sampling, no modulo bias)."""
        limit = ((1 << 64) // n) * n
        while True:
            x = self.next64()
            if x < limit: return x % n

    def randint(self, a, b):
        span = b - a + 1
        if span <= (1 << 64): return a + self.below(span)
        bits = span.bit_length() + 64
        while True:
            x = 0
            for _ in range((bits + 63) // 64): x = (x << 64) | self.next64()
            x &= (1 << bits) - 1
            if x < (1 << bits) // span * span: return a + x % span

    def choice(self, seq): return seq[self.below(len(seq))]
    def chance(self, num, den): return self.below(den) < num
    def randbytes(self, k): return bytes(self.below(256) for _ in range(k))
