# Simple Case
def scan1():
    return [
        (b'HomeNetwork', b'\x90r@\x1f\xf0\xe4', 11, -51, 3, False),
        (b'Telstra524E82', b'$\x7f RN\x88', 1, -71, 3, False),
        (b'Skynet', b'\x00\x04\xedL\xd3\xaf', 3, -82, 4, False),
        (b'Telstra2957', b'\x10\xdaC\xf6\x86\x87', 1, -86, 3, False),
        (b'Fon WiFi', b'\x12\xdaC\xf6\x86\x8a', 1, -86, 0, False),
        (b'Telstra Air', b'\x12\xdaC\xf6\x86\x89', 1, -87, 0, False),
        (b'NetComm ', b'\x18\x1fE\x15\x05"', 6, -91, 4, False)
    ]


# Two SSIDs one stronger than the other (Stronger is last to entice failure from lazy breaking)
def scan2():
    return [
        (b'HomeNetwork', b'\x90\'\xe4]"\xc5', 6, -83, 4, False),
        (b'Telstra524E82', b'$\x7f RN\x88', 1, -71, 3, False),
        (b'iiNet7580ED', b'\xe0\xb9\xe5u\x80\xed', 11, -82, 3, False),
        (b'Skynet', b'\x00\x04\xedL\xd3\xaf', 3, -83, 4, False),
        (b'HomeNetwork', b'\x90r@\x1f\xf0\xe4', 11, -51, 3, False),
        (b'SEC_LinkShare_f297a2', b'\xd0f{\n{\x15', 3, -92, 3, False),
        (b'HUAWEI-B315-D0B0', b'T\xb1! \xd0\xb0', 5, -92, 3, False),
        (b'NetComm ', b'\x18\x1fE\x15\x05"', 6, -95, 4, False)
    ]

# Test for not much going on
def scan3():
    return [
        (b'NetComm ', b'\x18\x1fE\x15\x05"', 6, -95, 4, False)
    ]