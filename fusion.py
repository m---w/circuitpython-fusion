# Sensor fusion for the micropython board. 22nd May 2015
# Ported to Python by Peter Hinch
# V0.2 Experimental. This is alpha quality code and needs further testing.

import pyb 
from math import sqrt, atan2, asin, degrees, radians
'''
Supports 6 and 9 degrees of freedom sensors. Tested with InvenSense MPU-9150 9DOF sensor.
Source https://github.com/xioTechnologies/Open-Source-AHRS-With-x-IMU.git
also https://github.com/kriswiner/MPU-9250.git
Ported to Python. Integrator timing adapted for pyboard.
User should repeatedly call the appropriate update method and extract the yaw pitch and roll angles as
reuired.
'''
class Fusion(object):
    '''
    Class provides sensor fusion allowing yaw, pitch and roll to be extracted. This uses the Madgwick algorithm.
    The update method must be called peiodically. The calculations take 1.6mS on the Pyboard. Suggested update
    rate 50Hz (20mS)
    '''
    declination = 0                         # Optional offset for true north. A +ve value adds to yaw (anticlockwise rotation)
    def __init__(self):
        self.magbias = (0, 0, 0)            # local magnetic bias factors: set from calibration
        self.start_time = None              # Time between updates
        self.q = [1.0, 0.0, 0.0, 0.0]       # vector to hold quaternion
        GyroMeasError = radians(40)         # Original code indicates this leads to a 2 sec response time
        self.beta = sqrt(3.0 / 4.0) * GyroMeasError  # compute beta (see README)

    def calibrate(self, getxyz, stopfunc):  # getxyz must return current magnetometer (x, y, z) tuple from the sensor
        magxyz = getxyz()                   # stopfunc (responding to time or user input) tells it to stop
        magmax = (v for v in magxyz)        # Initialise max and min iterators with current values
        magmin = (v for v in magxyz)
        while not stopfunc():
            pyb.delay(100)
            magxyz = getxyz()
            magmax = map(max, magmax, magxyz)
            magmin = map(min, magmin, magxyz)
        self.magbias = tuple(map(lambda a, b: (a +b)/2, magmin, magmax))

    @property
    def yaw(self):
        return self.declination + degrees(atan2(2.0 * (self.q[1] * self.q[2] + self.q[0] * self.q[3]),
            self.q[0] * self.q[0] + self.q[1] * self.q[1] - self.q[2] * self.q[2] - self.q[3] * self.q[3]))

    @property
    def pitch(self):
        return degrees(-asin(2.0 * (self.q[1] * self.q[3] - self.q[0] * self.q[2])))

    @property
    def roll(self):
        return degrees(atan2(2.0 * (self.q[0] * self.q[1] + self.q[2] * self.q[3]),
            self.q[0] * self.q[0] - self.q[1] * self.q[1] - self.q[2] * self.q[2] + self.q[3] * self.q[3]))

    def angles(self):
        yaw = degrees(atan2(2.0 * (self.q[1] * self.q[2] + self.q[0] * self.q[3]),
            self.q[0] * self.q[0] + self.q[1] * self.q[1] - self.q[2] * self.q[2] - self.q[3] * self.q[3]))
        pitch = degrees(-asin(2.0 * (self.q[1] * self.q[3] - self.q[0] * self.q[2])))
        roll  = degrees(atan2(2.0 * (self.q[0] * self.q[1] + self.q[2] * self.q[3]),
            self.q[0] * self.q[0] - self.q[1] * self.q[1] - self.q[2] * self.q[2] + self.q[3] * self.q[3]))
        return yaw + self.declination, pitch, roll

    def update_nomag(self, accel, gyro):    # 3-tuples (x, y, z) for accel, gyro
        ax, ay, az = accel                  # Units G (but later normalised)
        gx, gy, gz = (radians(x) for x in gyro) # Units deg/s
        if self.start_time is None:
            self.start_time = pyb.micros()  # First run
        q1, q2, q3, q4 = (self.q[x] for x in range(4))   # short name local variable for readability
        # Auxiliary variables to avoid repeated arithmetic
        _2q1 = 2 * q1
        _2q2 = 2 * q2
        _2q3 = 2 * q3
        _2q4 = 2 * q4
        _4q1 = 4 * q1
        _4q2 = 4 * q2
        _4q3 = 4 * q3
        _8q2 = 8 * q2
        _8q3 = 8 * q3
        q1q1 = q1 * q1
        q2q2 = q2 * q2
        q3q3 = q3 * q3
        q4q4 = q4 * q4

        # Normalise accelerometer measurement
        norm = sqrt(ax * ax + ay * ay + az * az)
        if (norm == 0):
            return # handle NaN
        norm = 1 / norm        # use reciprocal for division
        ax *= norm
        ay *= norm
        az *= norm

        # Gradient decent algorithm corrective step
        s1 = _4q1 * q3q3 + _2q3 * ax + _4q1 * q2q2 - _2q2 * ay
        s2 = _4q2 * q4q4 - _2q4 * ax + 4 * q1q1 * q2 - _2q1 * ay - _4q2 + _8q2 * q2q2 + _8q2 * q3q3 + _4q2 * az
        s3 = 4 * q1q1 * q3 + _2q1 * ax + _4q3 * q4q4 - _2q4 * ay - _4q3 + _8q3 * q2q2 + _8q3 * q3q3 + _4q3 * az
        s4 = 4 * q2q2 * q4 - _2q2 * ax + 4 * q3q3 * q4 - _2q3 * ay
        norm = 1 / sqrt(s1 * s1 + s2 * s2 + s3 * s3 + s4 * s4)    # normalise step magnitude
        s1 *= norm
        s2 *= norm
        s3 *= norm
        s4 *= norm

        # Compute rate of change of quaternion
        qDot1 = 0.5 * (-q2 * gx - q3 * gy - q4 * gz) - self.beta * s1
        qDot2 = 0.5 * (q1 * gx + q3 * gz - q4 * gy) - self.beta * s2
        qDot3 = 0.5 * (q1 * gy - q2 * gz + q4 * gx) - self.beta * s3
        qDot4 = 0.5 * (q1 * gz + q2 * gy - q3 * gx) - self.beta * s4

        # Integrate to yield quaternion
        deltat = pyb.elapsed_micros(self.start_time) / 1000000
        self.start_time = pyb.micros()
        q1 += qDot1 * deltat
        q2 += qDot2 * deltat
        q3 += qDot3 * deltat
        q4 += qDot4 * deltat
        norm = 1 / sqrt(q1 * q1 + q2 * q2 + q3 * q3 + q4 * q4)    # normalise quaternion
        self.q = q1 * norm, q2 * norm, q3 * norm, q4 * norm

    def update(self, accel, gyro, mag):     # 3-tuples (x, y, z) for accel, gyro and mag data
        mx, my, mz = (mag[x] - self.magbias[x] for x in range(3)) # Units uT
        ax, ay, az = accel                  # Units G (but later normalised)
        gx, gy, gz = (radians(x) for x in gyro)  # Units deg/s
        if self.start_time is None:
            self.start_time = pyb.micros()  # First run
        q1, q2, q3, q4 = (self.q[x] for x in range(4))   # short name local variable for readability
        # Auxiliary variables to avoid repeated arithmetic
        _2q1 = 2 * q1
        _2q2 = 2 * q2
        _2q3 = 2 * q3
        _2q4 = 2 * q4
        _2q1q3 = 2 * q1 * q3
        _2q3q4 = 2 * q3 * q4
        q1q1 = q1 * q1
        q1q2 = q1 * q2
        q1q3 = q1 * q3
        q1q4 = q1 * q4
        q2q2 = q2 * q2
        q2q3 = q2 * q3
        q2q4 = q2 * q4
        q3q3 = q3 * q3
        q3q4 = q3 * q4
        q4q4 = q4 * q4

        # Normalise accelerometer measurement
        norm = sqrt(ax * ax + ay * ay + az * az)
        if (norm == 0):
            return # handle NaN
        norm = 1 / norm                     # use reciprocal for division
        ax *= norm
        ay *= norm
        az *= norm

        # Normalise magnetometer measurement
        norm = sqrt(mx * mx + my * my + mz * mz)
        if (norm == 0):
            return                          # handle NaN
        norm = 1 / norm                     # use reciprocal for division
        mx *= norm
        my *= norm
        mz *= norm

        # Reference direction of Earth's magnetic field
        _2q1mx = 2 * q1 * mx
        _2q1my = 2 * q1 * my
        _2q1mz = 2 * q1 * mz
        _2q2mx = 2 * q2 * mx
        hx = mx * q1q1 - _2q1my * q4 + _2q1mz * q3 + mx * q2q2 + _2q2 * my * q3 + _2q2 * mz * q4 - mx * q3q3 - mx * q4q4
        hy = _2q1mx * q4 + my * q1q1 - _2q1mz * q2 + _2q2mx * q3 - my * q2q2 + my * q3q3 + _2q3 * mz * q4 - my * q4q4
        _2bx = sqrt(hx * hx + hy * hy)
        _2bz = -_2q1mx * q3 + _2q1my * q2 + mz * q1q1 + _2q2mx * q4 - mz * q2q2 + _2q3 * my * q4 - mz * q3q3 + mz * q4q4
        _4bx = 2 * _2bx
        _4bz = 2 * _2bz

        # Gradient descent algorithm corrective step
        s1 = (-_2q3 * (2 * q2q4 - _2q1q3 - ax) + _2q2 * (2 * q1q2 + _2q3q4 - ay) - _2bz * q3 * (_2bx * (0.5 - q3q3 - q4q4)
             + _2bz * (q2q4 - q1q3) - mx) + (-_2bx * q4 + _2bz * q2) * (_2bx * (q2q3 - q1q4) + _2bz * (q1q2 + q3q4) - my)
             + _2bx * q3 * (_2bx * (q1q3 + q2q4) + _2bz * (0.5 - q2q2 - q3q3) - mz))

        s2 = (_2q4 * (2 * q2q4 - _2q1q3 - ax) + _2q1 * (2 * q1q2 + _2q3q4 - ay) - 4 * q2 * (1 - 2 * q2q2 - 2 * q3q3 - az)
             + _2bz * q4 * (_2bx * (0.5 - q3q3 - q4q4) + _2bz * (q2q4 - q1q3) - mx) + (_2bx * q3 + _2bz * q1) * (_2bx * (q2q3 - q1q4)
             + _2bz * (q1q2 + q3q4) - my) + (_2bx * q4 - _4bz * q2) * (_2bx * (q1q3 + q2q4) + _2bz * (0.5 - q2q2 - q3q3) - mz))

        s3 = (-_2q1 * (2 * q2q4 - _2q1q3 - ax) + _2q4 * (2 * q1q2 + _2q3q4 - ay) - 4 * q3 * (1 - 2 * q2q2 - 2 * q3q3 - az)
             + (-_4bx * q3 - _2bz * q1) * (_2bx * (0.5 - q3q3 - q4q4) + _2bz * (q2q4 - q1q3) - mx)
             + (_2bx * q2 + _2bz * q4) * (_2bx * (q2q3 - q1q4) + _2bz * (q1q2 + q3q4) - my)
             + (_2bx * q1 - _4bz * q3) * (_2bx * (q1q3 + q2q4) + _2bz * (0.5 - q2q2 - q3q3) - mz))

        s4 = (_2q2 * (2 * q2q4 - _2q1q3 - ax) + _2q3 * (2 * q1q2 + _2q3q4 - ay) + (-_4bx * q4 + _2bz * q2) * (_2bx * (0.5 - q3q3 - q4q4)
              + _2bz * (q2q4 - q1q3) - mx) + (-_2bx * q1 + _2bz * q3) * (_2bx * (q2q3 - q1q4) + _2bz * (q1q2 + q3q4) - my)
              + _2bx * q2 * (_2bx * (q1q3 + q2q4) + _2bz * (0.5 - q2q2 - q3q3) - mz))

        norm = 1 / sqrt(s1 * s1 + s2 * s2 + s3 * s3 + s4 * s4)    # normalise step magnitude
        s1 *= norm
        s2 *= norm
        s3 *= norm
        s4 *= norm

        # Compute rate of change of quaternion
        qDot1 = 0.5 * (-q2 * gx - q3 * gy - q4 * gz) - self.beta * s1
        qDot2 = 0.5 * (q1 * gx + q3 * gz - q4 * gy) - self.beta * s2
        qDot3 = 0.5 * (q1 * gy - q2 * gz + q4 * gx) - self.beta * s3
        qDot4 = 0.5 * (q1 * gz + q2 * gy - q3 * gx) - self.beta * s4

        # Integrate to yield quaternion
        deltat = pyb.elapsed_micros(self.start_time) / 1000000
        self.start_time = pyb.micros()
        q1 += qDot1 * deltat
        q2 += qDot2 * deltat
        q3 += qDot3 * deltat
        q4 += qDot4 * deltat
        norm = 1 / sqrt(q1 * q1 + q2 * q2 + q3 * q3 + q4 * q4)    # normalise quaternion
        self.q = q1 * norm, q2 * norm, q3 * norm, q4 * norm
