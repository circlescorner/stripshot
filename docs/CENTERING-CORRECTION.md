# DS40 centering — accepted diagnostic result

The operator accepted Q3 as visually centered after reporting these middle-gauge
left/right distances to the 10 mm marks:

| Strip | Left | Right | Residual center offset |
|---|---:|---:|---|
| 1 | 9.4 mm | 10.1 mm | 0.35 mm left |
| 2 | 9.9 mm | 9.9 mm | centered |
| 3 | 9.7 mm | 10.0 mm | 0.15 mm left |
| 4 | 10.0 mm | 9.8 mm | 0.10 mm right |

Retain Q3 offsets, in left-to-right strip order: **+20, +15, +6, -2 pixels**
at 300 DPI; positive moves content right. No overall rescaling. Each strip is
clipped independently. Do not add another residual correction based on this
single accepted set. The earlier Q2 square measured 20 x 20 mm.

Q3 was one copy, job DNP_DS40-12, completed by CUPS and physically inspected.
Q1 (DNP_DS40-10) established four-strip cutting but showed progressive centering
error. Q2 (DNP_DS40-11) supplied measurements for Q3. All three jobs were
individually authorized and submitted once with durable intent records.

Queue DNP_DS40, Gutenprint 5.3.4; PageSize=w432h576-div4, Resolution=300dpi,
ColorModel=RGB, StpLaminate=Glossy, StpiShrinkOutput=Crop, StpNoCutWaste=False,
orientation-requested=4, number-up=1, copies=1. Calibration is specific to these
settings, the tested printer/media, and the 2400x1800 source sheet.

The accepted values are saved in ds40-accepted-calibration.json as evidence,
not an active application configuration. Application rendering has not adopted
the correction. Production artwork/photos and repeatability remain unqualified.
Application printing remains disabled; acceptance of centering did not authorize
removing that gate, further prints, or merging the draft PR.
