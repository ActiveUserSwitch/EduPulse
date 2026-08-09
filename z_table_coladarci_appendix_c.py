#!/usr/bin/env python3
"""
z_table_coladarci_appendix_c.py

Exact reproduction of the z-table (Areas under the Normal Curve) from:
    Coladarci, T., et al. "Fundamentals of Statistical Reasoning in Education"
    Appendix C, Table A.

This module provides lookup functions that match the printed textbook table EXACTLY.
It is intended for students learning z-scores (Chapter 6) and z-tests / p-values (Chapter 11).

The table gives, for positive z (to two decimal places):
    - Column 2: Area between the mean (z=0) and z
    - Column 3: Area beyond z (in the tail, away from the mean)

All lookups round the input z to two decimal places, exactly as one does when using
the printed table in the book.

NO external statistical libraries (e.g. scipy.stats) are used for the core lookup.
The values are hard-coded from the textbook so they match the book 100%.

Educational references:
    - Chapter 6: Normal distributions, z-scores, and areas under the curve.
    - Chapter 11: Using the unit normal table for z-tests, one- and two-tailed p-values,
      critical values for hypothesis testing at various alpha levels.
    - Appendix C, Table A: The source of all numeric values in this module.

Author: Generated for EduPulse / statistical reasoning coursework
"""

from typing import Union, Tuple

# =============================================================================
# EXACT Z-TABLE FROM COLADARCI ET AL. APPENDIX C, TABLE A
# =============================================================================
# Format: z (positive, 2 decimals): (Area_Between_Mean_and_z, Area_Beyond_z)
#
# These are the precise values from the textbook. Do not derive or approximate
# them with formulas or libraries if you want to match the book exactly.
# =============================================================================

z_table = {
    0.00: (0.0000, 0.5000),
    0.01: (0.0040, 0.4960),
    0.02: (0.0080, 0.4920),
    0.03: (0.0120, 0.4880),
    0.04: (0.0160, 0.4840),
    0.05: (0.0199, 0.4801),
    0.06: (0.0239, 0.4761),
    0.07: (0.0279, 0.4721),
    0.08: (0.0319, 0.4681),
    0.09: (0.0359, 0.4641),
    0.10: (0.0398, 0.4602),
    0.11: (0.0438, 0.4562),
    0.12: (0.0478, 0.4522),
    0.13: (0.0517, 0.4483),
    0.14: (0.0557, 0.4443),
    0.15: (0.0596, 0.4404),
    0.16: (0.0636, 0.4364),
    0.17: (0.0675, 0.4325),
    0.18: (0.0714, 0.4286),
    0.19: (0.0753, 0.4247),
    0.20: (0.0793, 0.4207),
    0.21: (0.0832, 0.4168),
    0.22: (0.0871, 0.4129),
    0.23: (0.0910, 0.4090),
    0.24: (0.0948, 0.4052),
    0.25: (0.0987, 0.4013),
    0.26: (0.1026, 0.3974),
    0.27: (0.1064, 0.3936),
    0.28: (0.1103, 0.3897),
    0.29: (0.1141, 0.3859),
    0.30: (0.1179, 0.3821),
    0.31: (0.1217, 0.3783),
    0.32: (0.1255, 0.3745),
    0.33: (0.1293, 0.3707),
    0.34: (0.1331, 0.3669),
    0.35: (0.1368, 0.3632),
    0.36: (0.1406, 0.3594),
    0.37: (0.1443, 0.3557),
    0.38: (0.1480, 0.3520),
    0.39: (0.1517, 0.3483),
    0.40: (0.1554, 0.3446),
    0.41: (0.1591, 0.3409),
    0.42: (0.1628, 0.3372),
    0.43: (0.1664, 0.3336),
    0.44: (0.1700, 0.3300),
    0.45: (0.1736, 0.3264),
    0.46: (0.1772, 0.3228),
    0.47: (0.1808, 0.3192),
    0.48: (0.1844, 0.3156),
    0.49: (0.1879, 0.3121),
    0.50: (0.1915, 0.3085),
    0.51: (0.1950, 0.3050),
    0.52: (0.1985, 0.3015),
    0.53: (0.2019, 0.2981),
    0.54: (0.2054, 0.2946),
    0.55: (0.2088, 0.2912),
    0.56: (0.2123, 0.2877),
    0.57: (0.2157, 0.2843),
    0.58: (0.2190, 0.2810),
    0.59: (0.2224, 0.2776),
    0.60: (0.2257, 0.2743),
    0.61: (0.2291, 0.2709),
    0.62: (0.2324, 0.2676),
    0.63: (0.2357, 0.2643),
    0.64: (0.2389, 0.2611),
    0.65: (0.2422, 0.2578),
    0.66: (0.2454, 0.2546),
    0.67: (0.2486, 0.2514),
    0.68: (0.2517, 0.2483),
    0.69: (0.2549, 0.2451),
    0.70: (0.2580, 0.2420),
    0.71: (0.2611, 0.2389),
    0.72: (0.2642, 0.2358),
    0.73: (0.2673, 0.2327),
    0.74: (0.2704, 0.2296),
    0.75: (0.2734, 0.2266),
    0.76: (0.2764, 0.2236),
    0.77: (0.2794, 0.2206),
    0.78: (0.2823, 0.2177),
    0.79: (0.2852, 0.2148),
    0.80: (0.2881, 0.2119),
    0.81: (0.2910, 0.2090),
    0.82: (0.2939, 0.2061),
    0.83: (0.2967, 0.2033),
    0.84: (0.2995, 0.2005),
    0.85: (0.3023, 0.1977),
    0.86: (0.3051, 0.1949),
    0.87: (0.3078, 0.1922),
    0.88: (0.3106, 0.1894),
    0.89: (0.3133, 0.1867),
    0.90: (0.3159, 0.1841),
    0.91: (0.3186, 0.1814),
    0.92: (0.3212, 0.1788),
    0.93: (0.3238, 0.1762),
    0.94: (0.3264, 0.1736),
    0.95: (0.3289, 0.1711),
    0.96: (0.3315, 0.1685),
    0.97: (0.3340, 0.1660),
    0.98: (0.3365, 0.1635),
    0.99: (0.3389, 0.1611),
    1.00: (0.3413, 0.1587),
    1.01: (0.3438, 0.1562),
    1.02: (0.3461, 0.1539),
    1.03: (0.3485, 0.1515),
    1.04: (0.3508, 0.1492),
    1.05: (0.3531, 0.1469),
    1.06: (0.3554, 0.1446),
    1.07: (0.3577, 0.1423),
    1.08: (0.3599, 0.1401),
    1.09: (0.3621, 0.1379),
    1.10: (0.3643, 0.1357),
    1.11: (0.3665, 0.1335),
    1.12: (0.3686, 0.1314),
    1.13: (0.3708, 0.1292),
    1.14: (0.3729, 0.1271),
    1.15: (0.3749, 0.1251),
    1.16: (0.3770, 0.1230),
    1.17: (0.3790, 0.1210),
    1.18: (0.3810, 0.1190),
    1.19: (0.3830, 0.1170),
    1.20: (0.3849, 0.1151),
    1.21: (0.3869, 0.1131),
    1.22: (0.3888, 0.1112),
    1.23: (0.3907, 0.1093),
    1.24: (0.3925, 0.1075),
    1.25: (0.3944, 0.1056),
    1.26: (0.3962, 0.1038),
    1.27: (0.3980, 0.1020),
    1.28: (0.3997, 0.1003),
    1.29: (0.4015, 0.0985),
    1.30: (0.4032, 0.0968),
    1.31: (0.4049, 0.0951),
    1.32: (0.4066, 0.0934),
    1.33: (0.4082, 0.0918),
    1.34: (0.4099, 0.0901),
    1.35: (0.4115, 0.0885),
    1.36: (0.4131, 0.0869),
    1.37: (0.4147, 0.0853),
    1.38: (0.4162, 0.0838),
    1.39: (0.4177, 0.0823),
    1.40: (0.4192, 0.0808),
    1.41: (0.4207, 0.0793),
    1.42: (0.4222, 0.0778),
    1.43: (0.4236, 0.0764),
    1.44: (0.4251, 0.0749),
    1.45: (0.4265, 0.0735),
    1.46: (0.4279, 0.0721),
    1.47: (0.4292, 0.0708),
    1.48: (0.4306, 0.0694),
    1.49: (0.4319, 0.0681),
    1.50: (0.4332, 0.0668),
    1.51: (0.4345, 0.0655),
    1.52: (0.4357, 0.0643),
    1.53: (0.4370, 0.0630),
    1.54: (0.4382, 0.0618),
    1.55: (0.4394, 0.0606),
    1.56: (0.4406, 0.0594),
    1.57: (0.4418, 0.0582),
    1.58: (0.4429, 0.0571),
    1.59: (0.4441, 0.0559),
    1.60: (0.4452, 0.0548),
    1.61: (0.4463, 0.0537),
    1.62: (0.4474, 0.0526),
    1.63: (0.4484, 0.0516),
    1.64: (0.4495, 0.0505),
    1.65: (0.4505, 0.0495),
    1.66: (0.4515, 0.0485),
    1.67: (0.4525, 0.0475),
    1.68: (0.4535, 0.0465),
    1.69: (0.4545, 0.0455),
    1.70: (0.4554, 0.0446),
    1.71: (0.4564, 0.0436),
    1.72: (0.4573, 0.0427),
    1.73: (0.4582, 0.0418),
    1.74: (0.4591, 0.0409),
    1.75: (0.4599, 0.0401),
    1.76: (0.4608, 0.0392),
    1.77: (0.4616, 0.0384),
    1.78: (0.4625, 0.0375),
    1.79: (0.4633, 0.0367),
    1.80: (0.4641, 0.0359),
    1.81: (0.4649, 0.0351),
    1.82: (0.4656, 0.0344),
    1.83: (0.4664, 0.0336),
    1.84: (0.4671, 0.0329),
    1.85: (0.4678, 0.0322),
    1.86: (0.4686, 0.0314),
    1.87: (0.4693, 0.0307),
    1.88: (0.4700, 0.0300),
    1.89: (0.4706, 0.0294),
    1.90: (0.4713, 0.0287),
    1.91: (0.4719, 0.0281),
    1.92: (0.4726, 0.0274),
    1.93: (0.4732, 0.0268),
    1.94: (0.4738, 0.0262),
    1.95: (0.4744, 0.0256),
    1.96: (0.4750, 0.0250),
    1.97: (0.4756, 0.0244),
    1.98: (0.4761, 0.0239),
    1.99: (0.4767, 0.0233),
    2.00: (0.4772, 0.0228),
    2.01: (0.4778, 0.0222),
    2.02: (0.4783, 0.0217),
    2.03: (0.4788, 0.0212),
    2.04: (0.4793, 0.0207),
    2.05: (0.4798, 0.0202),
    2.06: (0.4803, 0.0197),
    2.07: (0.4808, 0.0192),
    2.08: (0.4812, 0.0188),
    2.09: (0.4817, 0.0183),
    2.10: (0.4821, 0.0179),
    2.11: (0.4826, 0.0174),
    2.12: (0.4830, 0.0170),
    2.13: (0.4834, 0.0166),
    2.14: (0.4838, 0.0162),
    2.15: (0.4842, 0.0158),
    2.16: (0.4846, 0.0154),
    2.17: (0.4850, 0.0150),
    2.18: (0.4854, 0.0146),
    2.19: (0.4857, 0.0143),
    2.20: (0.4861, 0.0139),
    2.21: (0.4864, 0.0136),
    2.22: (0.4868, 0.0132),
    2.23: (0.4871, 0.0129),
    2.24: (0.4875, 0.0125),
    2.25: (0.4878, 0.0122),
    2.26: (0.4881, 0.0119),
    2.27: (0.4884, 0.0116),
    2.28: (0.4887, 0.0113),
    2.29: (0.4890, 0.0110),
    2.30: (0.4893, 0.0107),
    2.31: (0.4896, 0.0104),
    2.32: (0.4898, 0.0102),
    2.33: (0.4901, 0.0099),
    2.34: (0.4904, 0.0096),
    2.35: (0.4906, 0.0094),
    2.36: (0.4909, 0.0091),
    2.37: (0.4911, 0.0089),
    2.38: (0.4913, 0.0087),
    2.39: (0.4916, 0.0084),
    2.40: (0.4918, 0.0082),
    2.41: (0.4920, 0.0080),
    2.42: (0.4922, 0.0078),
    2.43: (0.4925, 0.0075),
    2.44: (0.4927, 0.0073),
    2.45: (0.4929, 0.0071),
    2.46: (0.4931, 0.0069),
    2.47: (0.4932, 0.0068),
    2.48: (0.4934, 0.0066),
    2.49: (0.4936, 0.0064),
    2.50: (0.4938, 0.0062),
    2.51: (0.4940, 0.0060),
    2.52: (0.4941, 0.0059),
    2.53: (0.4943, 0.0057),
    2.54: (0.4945, 0.0055),
    2.55: (0.4946, 0.0054),
    2.56: (0.4948, 0.0052),
    2.57: (0.4949, 0.0051),
    2.58: (0.4951, 0.0049),
    2.59: (0.4952, 0.0048),
    2.60: (0.4953, 0.0047),
    2.61: (0.4955, 0.0045),
    2.62: (0.4956, 0.0044),
    2.63: (0.4957, 0.0043),
    2.64: (0.4959, 0.0041),
    2.65: (0.4960, 0.0040),
    2.66: (0.4961, 0.0039),
    2.67: (0.4962, 0.0038),
    2.68: (0.4963, 0.0037),
    2.69: (0.4964, 0.0036),
    2.70: (0.4965, 0.0035),
    2.71: (0.4966, 0.0034),
    2.72: (0.4967, 0.0033),
    2.73: (0.4968, 0.0032),
    2.74: (0.4969, 0.0031),
    2.75: (0.4970, 0.0030),
    2.76: (0.4971, 0.0029),
    2.77: (0.4972, 0.0028),
    2.78: (0.4973, 0.0027),
    2.79: (0.4974, 0.0026),
    2.80: (0.4974, 0.0026),
    2.81: (0.4975, 0.0025),
    2.82: (0.4976, 0.0024),
    2.83: (0.4977, 0.0023),
    2.84: (0.4977, 0.0023),
    2.85: (0.4978, 0.0022),
    2.86: (0.4979, 0.0021),
    2.87: (0.4979, 0.0021),
    2.88: (0.4980, 0.0020),
    2.89: (0.4981, 0.0019),
    2.90: (0.4981, 0.0019),
    2.91: (0.4982, 0.0018),
    2.92: (0.4982, 0.0018),
    2.93: (0.4983, 0.0017),
    2.94: (0.4984, 0.0016),
    2.95: (0.4984, 0.0016),
    2.96: (0.4985, 0.0015),
    2.97: (0.4985, 0.0015),
    2.98: (0.4986, 0.0014),
    2.99: (0.4986, 0.0014),
    3.00: (0.4987, 0.0013),
    3.01: (0.4987, 0.0013),
    3.02: (0.4987, 0.0013),
    3.03: (0.4988, 0.0012),
    3.04: (0.4988, 0.0012),
    3.05: (0.4989, 0.0011),
    3.06: (0.4989, 0.0011),
    3.07: (0.4989, 0.0011),
    3.08: (0.4990, 0.0010),
    3.09: (0.4990, 0.0010),
    3.10: (0.4990, 0.0010),
    3.11: (0.4991, 0.0009),
    3.12: (0.4991, 0.0009),
    3.13: (0.4991, 0.0009),
    3.14: (0.4992, 0.0008),
    3.15: (0.4992, 0.0008),
    3.16: (0.4992, 0.0008),
    3.17: (0.4992, 0.0008),
    3.18: (0.4993, 0.0007),
    3.19: (0.4993, 0.0007),
    3.20: (0.4993, 0.0007),
    3.21: (0.4993, 0.0007),
    3.22: (0.4994, 0.0006),
    3.23: (0.4994, 0.0006),
    3.24: (0.4994, 0.0006),
    3.25: (0.4994, 0.0006),
    3.26: (0.4994, 0.0006),
    3.27: (0.4995, 0.0005),
    3.28: (0.4995, 0.0005),
    3.29: (0.4995, 0.0005),
    3.30: (0.4995, 0.0005),
    3.31: (0.4995, 0.0005),
    3.32: (0.4995, 0.0005),
    3.33: (0.4996, 0.0004),
    3.34: (0.4996, 0.0004),
    3.35: (0.4996, 0.0004),
    3.36: (0.4996, 0.0004),
    3.37: (0.4996, 0.0004),
    3.38: (0.4996, 0.0004),
    3.39: (0.4997, 0.0003),
    3.40: (0.4997, 0.0003),
    3.41: (0.4997, 0.0003),
    3.42: (0.4997, 0.0003),
    3.43: (0.4997, 0.0003),
    3.44: (0.4997, 0.0003),
    3.45: (0.4997, 0.0003),
    3.46: (0.4997, 0.0003),
    3.47: (0.4997, 0.0003),
    3.48: (0.4997, 0.0003),
    3.49: (0.4998, 0.0002),
    3.50: (0.4998, 0.0002),
    3.51: (0.4998, 0.0002),
    3.52: (0.4998, 0.0002),
    3.53: (0.4998, 0.0002),
    3.54: (0.4998, 0.0002),
    3.55: (0.4998, 0.0002),
    3.56: (0.4998, 0.0002),
    3.57: (0.4998, 0.0002),
    3.58: (0.4998, 0.0002),
    3.59: (0.4998, 0.0002),
    3.60: (0.4998, 0.0002),
    3.61: (0.4999, 0.0001),
    3.62: (0.4999, 0.0001),
    3.63: (0.4999, 0.0001),
    3.64: (0.4999, 0.0001),
    3.65: (0.4999, 0.0001),
    3.66: (0.4999, 0.0001),
    3.67: (0.4999, 0.0001),
    3.68: (0.4999, 0.0001),
    3.69: (0.4999, 0.0001),
    3.70: (0.4999, 0.0001),
}


def _normalize_z(z: float) -> float:
    """Round z to exactly two decimal places, as required when using the printed table."""
    return round(z, 2)


def _get_raw_entry(z: float) -> Union[Tuple[float, float], None]:
    """
    Internal helper. Returns the (area_between, area_beyond) tuple for |z|.
    Returns None if |z| > 3.70 (beyond table range).
    """
    z_rounded = _normalize_z(z)
    key = abs(z_rounded)
    if key > 3.70:
        return None
    # The table only stores non-negative keys
    return z_table.get(key)


def get_area_between(z: float) -> float:
    """
    Return the area between the mean and z (Column 2 of Appendix C, Table A).

    This is the proportion of the distribution that lies between z = 0 and the
    given z value. It is always positive and represents "how much of the curve
    is captured between the mean and this z-score".

    Negative z values are handled by symmetry (Chapter 6): the area between
    the mean and -1.23 is identical to the area between the mean and +1.23.

    If |z| > 3.70 (beyond the printed table), returns 0.4999 with a note.

    Args:
        z: The z-score (will be rounded to 2 decimal places).

    Returns:
        Area between mean and z (0.0000 to 0.4999).
    """
    entry = _get_raw_entry(z)
    if entry is None:
        print(f"NOTE: |z| = {abs(_normalize_z(z)):.2f} is beyond the table in "
              "Appendix C, Table A (max z = 3.70). "
              "Area between mean and z ≈ 0.4999 (almost the entire half of the curve).")
        return 0.4999
    return entry[0]


def get_tail_area(z: float) -> float:
    """
    Return the area in the tail beyond z (Column 3 of Appendix C, Table A).

    This value is the probability in the tail of the distribution away from the
    mean in the direction of z. For a positive z it is P(Z > z). For a negative
    z it is P(Z < z) (left tail). The numeric value depends only on |z| due to
    symmetry (Chapter 6).

    This column is the direct source for one-tailed p-values in z-tests (Chapter 11).

    If |z| > 3.70, returns a very small value (0.0001) with a note.

    Args:
        z: The z-score (rounded to 2 decimals internally).

    Returns:
        Tail probability (area beyond z).
    """
    entry = _get_raw_entry(z)
    if entry is None:
        print(f"NOTE: |z| = {abs(_normalize_z(z)):.2f} > 3.70 (beyond Appendix C, Table A). "
              "Tail area is extremely small (< 0.0001).")
        return 0.0001
    return entry[1]


def get_p_value(z: float, tails: int = 2) -> float:
    """
    Compute the p-value for a z-statistic using the textbook table.

    This function implements the logic from Chapter 11 (z-tests and p-values).

    - For a TWO-TAILED test (tails=2, the default for non-directional hypotheses):
      p = 2 × (area beyond |z|)
      This gives the probability of a result at least as extreme in either direction.

    - For a ONE-TAILED test (tails=1):
      p = area beyond z   (in the direction of the alternative hypothesis)
      IMPORTANT: The caller must pass z with the correct sign.
      Example: If you predict a positive effect and observed z = +2.10, use z=+2.10.
               If you predict a negative effect and observed z = -1.85, use z=-1.85.

    The resulting p-value is compared to alpha (e.g., 0.05) to decide whether to
    reject the null hypothesis.

    Args:
        z: Observed z-statistic.
        tails: 1 or 2 (default 2).

    Returns:
        p-value (between 0 and 1).
    """
    if tails not in (1, 2):
        raise ValueError("tails must be 1 or 2 (see Chapter 11 for one- vs two-tailed tests)")

    tail = get_tail_area(z)
    if tails == 2:
        p = 2 * tail
    else:
        p = tail

    # p-value cannot exceed 1.0
    return min(p, 1.0)


def find_critical_z(alpha: float, tails: int = 2) -> Union[float, Tuple[float, float]]:
    """
    Find the critical z-value(s) from Appendix C, Table A for a given alpha level.

    Critical values are the z-score(s) that leave exactly (or just under) the
    desired tail probability. They define the rejection region(s) in hypothesis
    testing (Chapter 11).

    - Two-tailed test (tails=2): returns a tuple (-crit, +crit)
      Example for α = 0.05: (-1.96, 1.96)
    - One-tailed test (tails=1): returns the positive critical value.
      The user applies the appropriate sign depending on the hypothesis.
      Example for α = 0.05 right-tailed: +1.65 (or 1.64/1.65 per table rounding)

    The search uses the Area_Beyond_z column to locate the z whose tail probability
    is closest to (and does not exceed) alpha / tails.

    Args:
        alpha: Significance level (e.g. 0.05, 0.01, 0.10). Must be between 0 and 1.
        tails: 1 or 2.

    Returns:
        For tails=2: tuple (negative_critical, positive_critical)
        For tails=1: positive critical z (float)
    """
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1 (exclusive)")

    if tails not in (1, 2):
        raise ValueError("tails must be 1 or 2")

    target_tail = alpha / tails

    # Find the z (to 2 decimal places) whose "Area Beyond" is closest to the
    # required tail probability. This is how students actually use printed
    # tables — they look for the value in Column 3 that most closely matches
    # the tail probability they need (alpha or alpha/2).
    #
    # We break ties by preferring the slightly more extreme z (smaller tail).
    best_z = None
    best_diff = float('inf')

    for z_val in sorted(z_table.keys()):
        tail_val = z_table[z_val][1]
        diff = abs(tail_val - target_tail)

        if diff < best_diff or (diff == best_diff and tail_val < z_table.get(best_z, (0, 1))[1]):
            best_z = z_val
            best_diff = diff

    if best_z is None:
        best_z = 3.70

    if tails == 2:
        return (-best_z, best_z)
    else:
        return best_z


# =============================================================================
# COMMAND-LINE INTERFACE (for piping data, batch validation, PhD workflow)
# =============================================================================

def _process_single(z: float, action: str, tails: int) -> dict:
    """Helper for CLI: compute requested values for one z."""
    z_r = _normalize_z(z)
    result = {"z_rounded": z_r, "z_input": z}

    if action in ("area", "all"):
        result["area_between_mean_and_z"] = get_area_between(z)
    if action in ("tail", "all"):
        result["area_beyond_z"] = get_tail_area(z)
    if action in ("p", "all"):
        result["p_value"] = get_p_value(z, tails=tails)
        result["tails"] = tails
    if action in ("critical", "all") and action == "critical":
        # handled separately
        pass
    return result


def main():
    """
    Main entry point with full CLI for interactive use, scripting, and piping data.

    This makes the textbook z-table a practical tool for your EduPulse validation
    work and PhD dissertation (exact Coladarci numbers instead of floating scipy).

    Examples of use:

    # 1. Quick single lookups (Chapter 6 / 11 style)
    python z_table_coladarci_appendix_c.py --z 1.96
    python z_table_coladarci_appendix_c.py --z 2.33 --p-value --tails 1
    python z_table_coladarci_appendix_c.py --critical --alpha 0.05 --tails 2

    # 2. Pipe data (one z per line)
    echo -e "1.96\n-2.58\n0.5\n4.2" | python z_table_coladarci_appendix_c.py --batch-stdin --tails 2

    # 3. Batch from CSV (common in validation: you have a column of observed z-stats
    #    from accuracy proportions, acoustic feature z-scores, or agreement rates)
    python z_table_coladarci_appendix_c.py \
        --batch-csv validation/my_z_results.csv \
        --z-column observed_z \
        --tails 2 \
        --add-columns area,tail,p \
        --output validation/my_z_results_with_textbook_p.csv

    # 4. JSON output for further scripting / reports
    python z_table_coladarci_appendix_c.py --z 1.96 --p-value --tails 2 --format json

    Inside Python (recommended for integration into validate_edupulse.py etc.):
        from z_table_coladarci_appendix_c import (
            get_area_between, get_tail_area, get_p_value, find_critical_z
        )
        p = get_p_value(my_observed_z, tails=2)
        crit = find_critical_z(0.05, tails=2)
    """
    import argparse
    import json
    import sys
    import csv
    from io import StringIO

    parser = argparse.ArgumentParser(
        description=(
            "Exact z-table lookups from Coladarci et al. \"Fundamentals of Statistical "
            "Reasoning in Education\", Appendix C, Table A.\n\n"
            "This tool is designed for EduPulse validation pipelines and PhD dissertation "
            "work. It guarantees textbook-exact values (no scipy approximation) so your "
            "reported p-values, areas, and critical values match the printed book exactly "
            "(Chapter 6 for normal curve interpretation, Chapter 11 for z-test p-values and critical regions)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Python API (recommended inside validation scripts):\n"
            "  from z_table_coladarci_appendix_c import (\n"
            "      get_area_between, get_tail_area, get_p_value, find_critical_z\n"
            "  )\n"
            "  p = get_p_value(my_z, tails=2)\n"
            "  crit = find_critical_z(0.05, tails=2)\n\n"
            "JSONL support is provided because EduPulse session manifests and many "
            "intermediate validation files are JSONL.\n\n"
            "Examples:\n"
            "  python z_table_coladarci_appendix_c.py --z 1.96 --p-value --tails 2\n"
            "  echo '1.96\n2.58' | python ... --batch-stdin --tails 2 --format csv\n"
            "  python ... --batch-jsonl validation/aligned_validation_data.jsonl \\\n"
            "             --z-key observed_z --add-columns area,tail,p --output ...csv\n"
            "  python ... --critical --alpha 0.05 --tails 2\n\n"
            "See the companion man page (z_table_coladarci.1) and the module docstring "
            "for full Chapter references and integration patterns with validate_edupulse.py."
        )
    )

    # Single-value modes
    parser.add_argument("--z", type=float, metavar="Z",
                        help="Single z-value to look up (will be rounded to 2 decimal places as in the printed table).")

    parser.add_argument("--p-value", action="store_true",
                        help="When used with --z, output the p-value (see --tails).")

    parser.add_argument("--critical", action="store_true",
                        help="Compute critical z-value(s) for a given alpha level instead of looking up a specific z.")

    parser.add_argument("--alpha", type=float, default=0.05, metavar="ALPHA",
                        help="Significance level for --critical (default: 0.05). Common values: 0.05, 0.01, 0.10.")

    parser.add_argument("--tails", type=int, choices=[1, 2], default=2,
                        help="Number of tails for p-value or critical value calculation. "
                             "2 = two-tailed (default, most common in Ch. 11 non-directional tests). "
                             "1 = one-tailed (use when you have a directional hypothesis; you must pass z with the correct sign).")

    # Batch / streaming modes (designed for validation pipelines and JSONL manifests)
    parser.add_argument("--batch-stdin", action="store_true",
                        help="Read one z-value per line from standard input (simple numeric stream). "
                             "Useful for quick pipes. Output format controlled by --format.")

    parser.add_argument("--batch-csv", metavar="FILE",
                        help="Process a CSV file. Adds textbook columns (area, tail, p-value) for the z column. "
                             "Requires --z-column. Writes to --output or stdout.")

    parser.add_argument("--batch-jsonl", metavar="FILE",
                        help="Process a JSONL file (one JSON object per line). This is the recommended mode for "
                             "EduPulse manifests and validation intermediate files. "
                             "Use --z-key to name the field containing the z-statistic. "
                             "Appends computed fields and writes JSONL or CSV depending on --format / --output.")

    parser.add_argument("--batch-jsonl-stdin", action="store_true",
                        help="Same as --batch-jsonl but read the JSONL stream from stdin. "
                             "Perfect for piping from other tools: cat manifest.jsonl | ... --batch-jsonl-stdin ...")

    parser.add_argument("--z-column", "--z-key", dest="z_key", default="z",
                        help="Name of the field/column that contains the observed z value. "
                             "For CSV: column name. For JSONL: key inside the JSON object. "
                             "Default: 'z' (also accepts 'observed_z', 'z_stat', etc. if you set it).")

    parser.add_argument("--add-columns", default="area,tail,p",
                        help="Comma-separated list of values to compute in batch mode. "
                             "Valid tokens: area (area between mean and z), tail (area beyond z), p (p-value). "
                             "Example: --add-columns area,tail,p")

    parser.add_argument("--output", metavar="FILE",
                        help="Write batch results to this file. Format is inferred from extension or --format. "
                             "If omitted, results go to stdout.")

    parser.add_argument("--format", choices=["human", "csv", "json", "jsonl"], default="human",
                        help="Output format for batch modes and single --p-value/--critical queries. "
                             "'jsonl' is useful when chaining tools. Default: human (pretty text).")

    parser.add_argument("--demo", action="store_true",
                        help="Run the built-in student-friendly demonstration examples (Chapter 6/11 style) and exit. "
                             "Useful for quick sanity checks or teaching.")

    args = parser.parse_args()

    # Demo mode (backwards compatible with old behavior)
    if args.demo or (len(sys.argv) == 1):
        # original demo code (kept for students)
        print("=" * 70)
        print("Z-TABLE LOOKUP — Coladarci et al., Appendix C, Table A")
        print("Exact textbook values (no scipy, no approximations)")
        print("=" * 70)

        for z in [1.96, 2.33]:
            area = get_area_between(z)
            tail = get_tail_area(z)
            p2 = get_p_value(z, tails=2)
            p1 = get_p_value(z, tails=1)
            print(f"\nz = {z}")
            print(f"  Area between mean and z: {area:.4f}")
            print(f"  Tail (beyond z):         {tail:.4f}")
            print(f"  p (two-tailed):          {p2:.4f}")
            print(f"  p (one-tailed):          {p1:.4f}")

        print("\nCritical z for α=0.05 (two-tailed):", find_critical_z(0.05, tails=2))
        print("Critical z for α=0.05 (one-tailed): ", find_critical_z(0.05, tails=1))
        print("\n(Use --help for piping / batch modes useful for validation work.)")
        return

    # --- Single z mode ---
    if args.z is not None and not args.batch_stdin and not args.batch_csv:
        z = args.z
        if args.critical:
            crit = find_critical_z(args.alpha, tails=args.tails)
            out = {"alpha": args.alpha, "tails": args.tails, "critical_z": crit}
        else:
            out = _process_single(z, "all" if not args.p_value else "p", args.tails)
            if args.p_value:
                out = {k: v for k, v in out.items() if k in ("z_rounded", "p_value", "tails")}

        if args.format == "json":
            print(json.dumps(out, indent=2))
        else:
            for k, v in out.items():
                print(f"{k}: {v}")
        return

    # --- Batch from stdin (great for simple pipes) ---
    if args.batch_stdin:
        lines = sys.stdin.read().strip().splitlines()
        zs = [float(line.strip()) for line in lines if line.strip()]
        results = []
        for z in zs:
            row = _process_single(z, "all", args.tails)
            results.append(row)

        if args.format == "json":
            print(json.dumps(results, indent=2))
        elif args.format == "csv" or args.output:
            # write CSV
            if results:
                keys = list(results[0].keys())
                if args.output:
                    with open(args.output, "w", newline="") as f:
                        writer = csv.DictWriter(f, fieldnames=keys)
                        writer.writeheader()
                        writer.writerows(results)
                    print(f"Wrote {len(results)} rows to {args.output}")
                else:
                    writer = csv.DictWriter(sys.stdout, fieldnames=keys)
                    writer.writeheader()
                    writer.writerows(results)
        else:
            for r in results:
                print(f"z={r['z_rounded']:.2f}  area={r.get('area_between_mean_and_z', 'N/A'):.4f}  "
                      f"tail={r.get('area_beyond_z', 'N/A'):.4f}  p({r.get('tails', args.tails)}t)={r.get('p_value', 'N/A'):.4f}")
        return

    # --- Batch from CSV (most powerful for validation / dissertation data) ---
    if args.batch_csv:
        import pandas as pd   # pandas is already used heavily in the validation pipeline

        df = pd.read_csv(args.batch_csv)
        if args.z_key not in df.columns:
            print(f"ERROR: Column '{args.z_key}' not found in {args.batch_csv}")
            print(f"Available columns: {list(df.columns)}")
            sys.exit(1)

        cols_to_add = [c.strip() for c in args.add_columns.split(",")]

        for idx, row in df.iterrows():
            z = row[args.z_key]
            try:
                zf = float(z)
            except (ValueError, TypeError):
                continue

            if "area" in cols_to_add:
                df.at[idx, "textbook_area_between"] = get_area_between(zf)
            if "tail" in cols_to_add:
                df.at[idx, "textbook_tail_area"] = get_tail_area(zf)
            if "p" in cols_to_add:
                df.at[idx, f"textbook_p_{args.tails}t"] = get_p_value(zf, tails=args.tails)

        if args.output:
            df.to_csv(args.output, index=False)
            print(f"Augmented CSV written to {args.output} ({len(df)} rows)")
        else:
            print(df.to_csv(index=False))
        return

    # --- Batch from JSONL (EduPulse native format - manifests, validation intermediates, etc.) ---
    def _process_jsonl_stream(lines, z_key, add_cols, tails, out_format, output_path):
        """Shared handler for --batch-jsonl and --batch-jsonl-stdin."""
        import json as _json

        results = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                obj = _json.loads(line)
            except Exception:
                continue

            z_val = obj.get(z_key)
            if z_val is None:
                # try common alternative names
                for alt in ("observed_z", "z_stat", "zscore", "z_score"):
                    if alt in obj:
                        z_val = obj[alt]
                        break
            if z_val is None:
                continue

            try:
                zf = float(z_val)
            except (ValueError, TypeError):
                continue

            row = {"z": _normalize_z(zf)}
            if "area" in add_cols:
                row["textbook_area_between"] = get_area_between(zf)
            if "tail" in add_cols:
                row["textbook_tail_area"] = get_tail_area(zf)
            if "p" in add_cols:
                row[f"textbook_p_{tails}t"] = get_p_value(zf, tails=tails)

            # carry forward some useful context if present
            for carry in ("audio_file", "tx_id", "day", "metric"):
                if carry in obj:
                    row[carry] = obj[carry]

            results.append(row)

        if not results:
            print("No valid z values found in JSONL stream.")
            return

        if out_format == "jsonl":
            if output_path:
                with open(output_path, "w") as f:
                    for r in results:
                        f.write(_json.dumps(r) + "\n")
                print(f"Wrote {len(results)} JSONL records to {output_path}")
            else:
                for r in results:
                    print(_json.dumps(r))
        elif out_format == "csv":
            import csv as _csv
            if results:
                keys = list(results[0].keys())
                if output_path:
                    with open(output_path, "w", newline="") as f:
                        w = _csv.DictWriter(f, fieldnames=keys)
                        w.writeheader()
                        w.writerows(results)
                    print(f"Wrote {len(results)} rows to {output_path}")
                else:
                    w = _csv.DictWriter(sys.stdout, fieldnames=keys)
                    w.writeheader()
                    w.writerows(results)
        else:
            # human or json
            if output_path:
                with open(output_path, "w") as f:
                    _json.dump(results, f, indent=2)
                print(f"Wrote {len(results)} records to {output_path}")
            else:
                for r in results:
                    print(r)

    if args.batch_jsonl:
        with open(args.batch_jsonl) as f:
            lines = f.readlines()
        add_cols = [c.strip() for c in args.add_columns.split(",")]
        _process_jsonl_stream(lines, args.z_key, add_cols, args.tails,
                              args.format, args.output)
        return

    if args.batch_jsonl_stdin:
        lines = sys.stdin.readlines()
        add_cols = [c.strip() for c in args.add_columns.split(",")]
        _process_jsonl_stream(lines, args.z_key, add_cols, args.tails,
                              args.format, args.output)
        return

    # If we get here with --critical but no z, do the critical lookup
    if args.critical:
        crit = find_critical_z(args.alpha, tails=args.tails)
        out = {"alpha": args.alpha, "tails": args.tails, "critical_z": crit}
        if args.format in ("json", "jsonl"):
            print(json.dumps(out, indent=2))
        else:
            print(f"Critical z for alpha={args.alpha}, tails={args.tails}: {crit}")
        return

    # Fallback help
    parser.print_help()


if __name__ == "__main__":
    main()
