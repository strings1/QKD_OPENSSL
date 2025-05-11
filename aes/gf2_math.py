from __future__ import annotations

class GF2Element:
    def __init__(self, backing_value: int):
        self.poly = backing_value & 0xFF # strip to one byte

    @staticmethod
    def mod_poly() -> GF2Element:
        p = GF2Element(0x00)
        p.poly = 0x11B # x^8 + x^4 + x^3 + x + 1
        return p

    def __add__(self, other: GF2Element) -> GF2Element:
        return GF2Element(self.poly ^ other.poly)

    def __sub__(self, other: GF2Element)-> GF2Element:
        return GF2Element(self.poly ^ other.poly)

    def __neg__(self) -> GF2Element:
        return GF2Element(self.poly)

    def __eq__(self, other: GF2Element) -> bool:
        return isinstance(other, GF2Element) and self.poly == other.poly

    def __abs__(self) -> GF2Element:
        return self

    def __str__(self) -> str:
        return hex(self.poly)

    def __mul__(self, other: GF2Element) -> GF2Element:
        result: GF2Element = GF2Element(0x00)
        lhs: GF2Element = GF2Element(self.poly)
        rhs: GF2Element = GF2Element(other.poly)

        while rhs.poly != 0:
            if (rhs.poly & 0x01) == 1:
                result = result + lhs

            lhs = lhs.xtimes()
            rhs = GF2Element(rhs.poly >> 1)

        return result

    def __truediv__(self, other: GF2Element) -> GF2Element:
        return self * other.inverse()
    
    def __div__(self, other: GF2Element) -> GF2Element:
        return self * other.inverse()

    def poly_math_str(self) -> str:
        out = str()
        cpy = GF2Element(self.poly)
        i = 7
        
        if cpy.poly == 0:
            return "0"

        while i >= 0:
            coeff = (cpy.poly & 0x80) == 0x80

            if coeff == True:
                out += f"x^{i} + "

            i = i-1
            cpy = GF2Element(cpy.poly << 1)

        return out[:-3] # strip last ' + '

    def xtimes(self) -> GF2Element:
        if (self.poly & 0x80) == 0x00:
            return GF2Element(self.poly << 1)
        elif (self.poly & 0x80) == 0x80:
            return (GF2Element(self.poly << 1) + GF2Element(0x1B))

    def inverse(self) -> GF2Element:
        out = GF2Element(1)
        for i in range(0,254):
            out = out * self
        return out

    @staticmethod
    def dot_product(lhs: [GF2Element], rhs: [GF2Element]) -> GF2Element:
        if len(lhs) != len(rhs):
            raise ValueError("Lists do not have the same length!")

        out = GF2Element(0)
        for i in range(0, len(lhs)):
            out += lhs[i] * rhs[i]