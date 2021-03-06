#!/usr/bin/env python
from datetime import datetime, timedelta
import struct

fit_file_id = {
    'type': 0,
    'serial': 3,
    'manufacturer': 1,
    'time_created': 3,
    'product': 2,
    'number': 5}

fit_lap = {
    'message_index': 254,
    'timestamp': 253,
    'event': 0,
    'event_type': 1,
    'start_time': 2,
    'start_lat': 3,
    'start_lon': 4,
    'end_lat': 5,
    'end_lon': 6,
    'elapsed_time': 7,
    'timer_time': 8,
    'distance': 9,
    'cycles': 10,
    'calories': 11,
    'fat_calories': 12,
    'avg_speed': 13,
    'max_speed': 14,
    'avg_hr': 15,
    'max_hr': 16,
    'avg_cadence': 17,
    'max_cadence': 18,
    'avg_power': 19,
    'max_power': 20,
    'ascent': 21,
    'descent': 22,
    'intensity': 23,
    'trigger': 24,
    'sport': 25,
    'event_group': 26}

fit_record = {
    'timestamp': 253,
    'lat': 0,
    'lon': 1,
    'distance': 5,
    'time_from_course': 11,
    'speed_distance': 8,
    'hr': 3,
    'alt': 2,
    'speed': 6,
    'power': 7,
    'grade': 9,
    'cadence': 4,
    'resistance': 10,
    'cycle_length': 12,
    'temperature': 13}

fit_session = {
    'timestamp': 253,
    'start_time': 2,
    'start_lat': 3,
    'start_lon': 4,
    'elapsed_time': 7,
    'timer_time': 8,
    'distance': 9,
    'cycles': 10,
    'calories': 11,
    'avg_speed': 14,
    'max_speed': 15,
    'avg_power': 20,
    'max_power': 21,
    'ascent': 22,
    'descent': 23,
    'first_lap': 25,
    'laps': 26,
    'avg_hr': 16,
    'max_hr': 17,
    'avg_cad': 18,
    'max_cad': 19}

fit_file_type = {
    1:  'device',
    2:  'settings',
    3:  'sport',
    4:  'activity',
    5:  'workout',
    9:  'weight',
    10: 'totals',
    11: 'goals',
    12: 'blood pressure'}

fit_msg_type = {
    0:  'file id',
    1:  'capabilites',
    2:  'device settings',
    3:  'user profile',
    4:  'HRM profile',
    5:  'SDM profile',
    6:  'bike profile',
    7:  'zones target',
    8:  'HR zone',
    9:  'power zone',
    10: 'met zone',
    12: 'sport',
    15: 'training goals',
    18: 'session',
    19: 'lap',
    20: 'record',
    21: 'event',
    22: 'unknown',
    23: 'device info',
    26: 'workout',
    27: 'workout step',
    30: 'weight scale',
    33: 'totals',
    34: 'activity',
    35: 'software',
    37: 'file capabilities',
    38: 'mesg capabilities',
    39: 'field capabilities',
    49: 'file creator',
    51: 'blood pressure',
    int('0xFF00', 16): 'mfg range min',
    int('0xFFFE', 16): 'mfg range max'}

fit_base_types = {
    0:  {'number':  0, 'endian': 0, 'field': int('0x00' ,16), 'type': 'enum',    'invalid': int('0xFF' ,16),               'size': 1},
    1:  {'number':  1, 'endian': 0, 'field': int('0x01' ,16), 'type': 'sint8',   'invalid': int('0x7F' ,16),               'size': 1},
    2:  {'number':  2, 'endian': 0, 'field': int('0x02' ,16), 'type': 'uint8',   'invalid': int('0xFF' ,16),               'size': 1},
    3:  {'number':  3, 'endian': 1, 'field': int('0x83' ,16), 'type': 'sint16',  'invalid': int('0x7FFF' ,16),             'size': 2},
    4:  {'number':  4, 'endian': 1, 'field': int('0x84' ,16), 'type': 'uint16',  'invalid': int('0xFFFF' ,16),             'size': 2},
    5:  {'number':  5, 'endian': 1, 'field': int('0x85' ,16), 'type': 'sint32',  'invalid': int('0x7FFFFFFF' ,16),         'size': 4},
    6:  {'number':  6, 'endian': 1, 'field': int('0x86' ,16), 'type': 'uint32',  'invalid': int('0xFFFFFFFF' ,16),         'size': 4},
    7:  {'number':  7, 'endian': 0, 'field': int('0x07' ,16), 'type': 'string',  'invalid': int('0x00' ,16),               'size': 1},
    8:  {'number':  8, 'endian': 1, 'field': int('0x88' ,16), 'type': 'float32', 'invalid': int('0xFFFFFFFF' ,16),         'size': 2},
    9:  {'number':  9, 'endian': 1, 'field': int('0x89' ,16), 'type': 'float64', 'invalid': int('0xFFFFFFFFFFFFFFFF' ,16), 'size': 4},
    10: {'number': 10, 'endian': 0, 'field': int('0x0A' ,16), 'type': 'uint8z',  'invalid': int('0x00' ,16),               'size': 1},
    11: {'number': 11, 'endian': 1, 'field': int('0x8B' ,16), 'type': 'uint16z', 'invalid': int('0x0000' ,16),             'size': 2},
    12: {'number': 12, 'endian': 1, 'field': int('0x8C' ,16), 'type': 'uint32z', 'invalid': int('0x00000000' ,16),         'size': 4},
    13: {'number': 13, 'endian': 0, 'field': int('0x0D' ,16), 'type': 'byte',    'invalid': int('0xFF' ,16),               'size': 1}}

fit_type_unpack = {
    'enum':    'B',
    'sint8':   'b',
    'uint8':   'B',
    'sint16':  'h',
    'uint16':  'H',
    'sint32':  'i',
    'uint32':  'I',
    'string':  'c',
    'float32': 'f',
    'float64': 'd',
    'uint8z':  'B',
    'uint16z': 'H',
    'uint32z': 'I',
    'byte':    'c'}

'''Timestamps are referenced from 1989-12-31 00:00 UTC,
   so we have to add the bit missing from where 0 timestamp normally is.'''
timestamp_offset = datetime(1989,12,31,00,00,00)-datetime.utcfromtimestamp(0)
'''latitude/longitude is stored in semicircles,
   this is the appropriate conversion factor to get degrees.'''
semicircle_deg = 180./(2**31)

def get_field_value(fields, field_def, field_name):
    try:
        field = fields[field_def[field_name]]
        value = field['value']
        if value == field['base_type']['invalid']:
            value = None
    except KeyError:
        value = None
    return value

class FITEntry(object):
    def __init__(self, time, hr, speed, cadence, power, temp, altitude, lat, lon, distance):
        self.time = time
        self.hr = hr
        self.speed = speed
        self.cadence = cadence
        self.power = power
        self.temp = temp
        self.altitude = altitude
        self.lon = lon
        self.lat = lat
        self.distance = distance

    def __str__(self):
        return '[%s] hr: %s spd: %s cad: %s pwr: %s temperature: %s alt: %s lat: %s lon: %s distance: %s' % (self.time, self.hr, self.speed, self.cadence, self.power, self.temp, self.altitude, self.lat, self.lon, self.distance)

class FITLap(object):
    def __init__(self, time, start_lon, start_lat, end_lon, end_lat,
                 distance, duration, ascent, descent, max_speed, avg_speed,
                 max_hr, avg_hr, avg_cadence, max_cadence, avg_power,
                 max_power, avg_temp, max_temp, min_temp, calories):
        self.start_time = time
        self.start_lon = start_lon
        self.start_lat = start_lat
        self.end_lon = end_lon
        self.end_lat = end_lat
        self.distance = distance
        self.duration = duration
        self.ascent = ascent
        self.descent = descent
        self.max_speed = max_speed
        self.avg_speed = avg_speed
        self.max_hr = max_hr
        self.avg_hr = avg_hr
        self.avg_cadence = avg_cadence
        self.max_cadence = max_cadence
        self.avg_power = avg_power
        self.max_power = max_power
        self.avg_temp = avg_temp
        self.max_temp = max_temp
        self.min_temp = min_temp
        self.temperature = self.avg_temp
        self.kcal = calories
    def __str__(self):
        return '[%s] duration: %s distance: %s power: %s start_lat: %s start_lon: %s' % (self.start_time, self.duration, self.distance, self.avg_power,self.start_lat, self.start_lon)

class FITParser(object):
    def __init__(self):
        self.start_lon = 0.0
        self.start_lat = 0.0
        self.end_lon = 0.0
        self.end_lat = 0.0
        self.entries = []
        self.distance_sum = 0.0
        self.ascent = 0.0
        self.descent = 0.0
        self.max_speed = 0
        self.avg_speed = 0
        self.max_hr = 0
        self.avg_hr = 0
        self.avg_cadence = 0
        self.max_cadence = 0
        self.avg_power = 0
        self.max_power = 0
        self.avg_torque = 0.0
        self.max_torque = 0.0
        self.avg_pedaling_cad = 0
        self.avg_pedaling_power = 0
        self.avg_temp = 0.0
        self.max_temp = 0.0
        self.min_temp = 0.0
        self.temperature = 0
        self.kcal_sum = 0
        self.laps = []

    def parse_uploaded_file(self, f):
        local_msg_types = {}
        hdr = f.read(12)
        (hdr_size,proto_ver,prof_ver,data_size) = struct.unpack('BBHI',hdr[0:8])
        data_type = hdr[8:]

        if data_type != '.FIT':
            return

        record_last_time = 0
        records = 0
        while f.tell() < data_size + hdr_size:
            (hdr,) = struct.unpack('B',f.read(1))
            hdr_type = (hdr >> 7) & 1

            if hdr_type == 0:
                msg_type = (hdr >> 6) & 1
                local_msg_type = (hdr) & int('1111',2)
            elif hdr_type == 1:
                '''
                TODO
                Compressed timestamp headers are not invalid,
                but not really handled properly either.
                '''
                continue
                local_msg_type = (hdr >> 5) & int('11',2)
            else:
                print hdr_type
                '''
                Invalid header type.
                '''
                return

            if msg_type == 0:
                fields = {}
                if local_msg_type not in local_msg_types:
                    continue
                global_msg_type = local_msg_types[local_msg_type]['global_msg_number']

                for field in local_msg_types[local_msg_type]['fields']:
                    base_type = fit_base_types[field['base_type']]
                    endian = local_msg_types[local_msg_type]['endian']
                    unpack_string = fit_type_unpack[base_type['type']]
                    field_data = f.read(base_type['size'])
                    if field['endian']:
                        unpack_string = endian + unpack_string
                    (field_value,) = struct.unpack(unpack_string, field_data)
                    fields[field['def_num']] = {'value': field_value, 'base_type': base_type}
                if global_msg_type == 0:
                    if get_field_value(fields, fit_file_id, 'type') != 4:
                        '''
                        Will only parse activity files.
                        '''
                        return
                elif global_msg_type == 18:
                    self.distance_sum = get_field_value(fields, fit_session, 'distance')
                    if self.distance_sum != None:
                        self.distance_sum = self.distance_sum / 100.
                    self.duration = ('%ss') % (int(round(get_field_value(fields, fit_session, 'timer_time')/1000.)))
                    self.start_lat = get_field_value(fields, fit_session, 'start_lat')
                    self.start_lon = get_field_value(fields, fit_session, 'start_lon')
                    if self.start_lat != None and self.start_lon != None:
                        self.start_lat = self.start_lat * semicircle_deg
                        self.start_lon = self.start_lon * semicircle_deg
                    self.avg_hr = get_field_value(fields, fit_session, 'avg_hr')
                    self.max_hr = get_field_value(fields, fit_session, 'max_hr')
                    self.avg_speed = get_field_value(fields, fit_session, 'avg_speed')
                    self.max_speed = get_field_value(fields, fit_session, 'max_speed')
                    if self.avg_speed != None and self.max_speed != None:
                        self.avg_speed = self.avg_speed/1000.*3.6
                        self.max_speed = self.max_speed/1000.*3.6
                    self.avg_cadence = get_field_value(fields, fit_session, 'avg_cad')
                    self.max_cadence = get_field_value(fields, fit_session, 'max_cad')
                    self.avg_power = get_field_value(fields, fit_session, 'avg_power')
                    self.max_power = get_field_value(fields, fit_session, 'max_power')
                    self.kcal_sum = get_field_value(fields, fit_session, 'calories')
                elif global_msg_type == 19:
                    '''
                    print '%i: %s %s %s' % (global_msg_type, fit_msg_type[global_msg_type],
                                            get_field_value(fields, fit_lap, 'event'),
                                            get_field_value(fields, fit_lap, 'event_type'))
                    '''

                    if (int(round(get_field_value(fields, fit_lap, 'timer_time')/1000.)) <= 1):
                        '''
                        Lets not bother with intervals of 1s or less. They tend to have
                        no sensible values anyways.
                        '''
                        continue

                    time = datetime.fromtimestamp(get_field_value(fields, fit_lap, 'timestamp'))
                    time = time + timestamp_offset
                    start_time = get_field_value(fields, fit_lap, 'start_time')
                    if start_time != None:
                        start_time = datetime.fromtimestamp(start_time)
                        start_time = start_time + timestamp_offset
                    distance = get_field_value(fields, fit_lap, 'distance')
                    if distance != None:
                        distance = distance / 100.
                    duration = ('%s') % (int(round(get_field_value(fields, fit_lap, 'timer_time')/1000.)))
                    start_lat = get_field_value(fields, fit_lap, 'start_lat')
                    start_lon = get_field_value(fields, fit_lap, 'start_lon')
                    if start_lat != None and start_lon != None:
                        start_lat = start_lat * semicircle_deg
                        start_lon = start_lon * semicircle_deg
                    end_lat = get_field_value(fields, fit_lap, 'end_lat')
                    end_lon = get_field_value(fields, fit_lap, 'end_lon')
                    if end_lat != None and end_lon != None:
                        end_lat = end_lat * semicircle_deg
                        end_lon = end_lon * semicircle_deg
                    avg_hr = get_field_value(fields, fit_lap, 'avg_hr')
                    max_hr = get_field_value(fields, fit_lap, 'max_hr')
                    avg_speed = get_field_value(fields, fit_lap, 'avg_speed')
                    max_speed = get_field_value(fields, fit_lap, 'max_speed')
                    if avg_speed != None and max_speed != None:
                        avg_speed = avg_speed/1000.*3.6
                        max_speed = max_speed/1000.*3.6
                    avg_cadence = get_field_value(fields, fit_lap, 'avg_cad')
                    max_cadence = get_field_value(fields, fit_lap, 'max_cad')
                    avg_power = get_field_value(fields, fit_lap, 'avg_power')
                    max_power = get_field_value(fields, fit_lap, 'max_power')
                    calories = get_field_value(fields, fit_lap, 'calories')
                    ascent = get_field_value(fields, fit_lap, 'ascent')
                    descent = get_field_value(fields, fit_lap, 'descent')
                    avg_temp = get_field_value(fields, fit_lap, 'avg_temp')
                    max_temp = get_field_value(fields, fit_lap, 'max_temp')
                    min_temp = get_field_value(fields, fit_lap, 'min_temp')

                    if start_time != None: # Do not add invalid intervals
                        self.laps.append(FITLap(start_time, start_lon, start_lat,
                                            end_lon, end_lat, distance, duration, ascent,
                                            descent, max_speed, avg_speed, max_hr,
                                            avg_hr, avg_cadence, max_cadence,
                                            avg_power, max_power, avg_temp, max_temp,
                                            min_temp, calories))
                elif global_msg_type == 20:
                    time = datetime.fromtimestamp(get_field_value(fields, fit_record, 'timestamp'))
                    if time == None:
                        '''
                        Samples without timestamp are broken
                        '''
                        continue
                    if time == record_last_time:
                        '''
                        Samples with duplicate timestamps are equally broken.
                        We make a crude attempt at fixing this by bumping the
                        previous sample 1s back.
                        If there is already a sample at 1s back, this usually
                        has the wrong time as well and there will be a larger
                        gap somewhere earlier, but as of now we just give up
                        and drop the current sample if that is the case.
                        '''
                        if (len(self.entries) == 1 or len(self.entries)>1 and (self.entries[-1].time - self.entries[-2].time).seconds != 1):
                            self.entries[-1].time = self.entries[-1].time - timedelta(seconds=1)
                        else:
                            continue

                    record_last_time = time
                    time = time + timestamp_offset
                    hr = get_field_value(fields, fit_record, 'hr')
                    pwr = get_field_value(fields, fit_record, 'power')
                    alt = get_field_value(fields, fit_record, 'alt')
                    if alt != None:
                        alt = alt/5. - 500
                    lat = get_field_value(fields, fit_record, 'lat')
                    lon = get_field_value(fields, fit_record, 'lon')
                    if lat != None and lon != None:
                        lat = lat*semicircle_deg
                        lon = lon*semicircle_deg
                    spd = get_field_value(fields, fit_record, 'speed')
                    if spd != None:
                        spd = spd/1000.*3.6
                    grade = get_field_value(fields, fit_record, 'grade')
                    temp = get_field_value(fields, fit_record, 'temperature')
                    cad = get_field_value(fields, fit_record, 'cadence')
                    distance = get_field_value(fields, fit_record, 'distance')
                    if distance != None:
                        distance = distance / 100.

                    #if distance == None or spd == None:
                        # Do not export samples like this
                        # Observed in site_media/turan/sensor/2011-06-18-12-55-11.fit
                    #    continue

                    self.entries.append(FITEntry(time,hr,spd,cad,pwr,temp,alt, lat, lon, distance))
                elif global_msg_type == 21:
                    '''
                    print '%i: %s' % (global_msg_type, fit_msg_type[global_msg_type])
                    for field in fields:
                        print '%i: %s' % (field, fields[field])
                    '''
                    pass
                '''
                else:
                    print '%i: %s' % (global_msg_type, fit_msg_type[global_msg_type])
                '''
            elif msg_type == 1:
                def_hdr = f.read(5)
                (arch,) = struct.unpack('B',def_hdr[1:2])
                if arch == 0:
                    endian = '<'
                elif arch == 1:
                    endian = '>'

                (global_msg_number,n_fields) = struct.unpack(endian + 'HB',def_hdr[2:5])

                fields = []
                for i in range(n_fields):
                    (field_def_num,field_size,base_type) = struct.unpack('BBB',f.read(3))
                    field_endian = (base_type >> 7) & 1
                    field_base_type = (base_type) & int('11111', 2)
                    fields.append({'def_num': field_def_num, 'size': field_size, 'endian': field_endian, 'base_type': field_base_type})
                local_msg_types[local_msg_type] = {'arch': arch, 'endian': endian, 'global_msg_number': global_msg_number, 'fields': fields}

        if self.entries:
            self.start_time = self.entries[0].time.time()
            self.date = self.entries[0].time.date()
            if self.start_lon == None or self.start_lat == None:
                self.start_lon = self.entries[0].lon
                self.start_lat = self.entries[0].lat
            self.end_lon = self.entries[-1].lon
            self.end_lat = self.entries[-1].lat

            pedaling_cad = 0
            pedaling_cad_seconds = 0
            pedaling_power = 0
            pedaling_power_seconds = 0

            temp = 0
            temp_seconds = 0
            max_temp = -273.15
            min_temp = 273.15

            last = self.entries[0].time
            for e in self.entries:
                interval = (e.time - last).seconds
                if e.cadence != None and e.cadence > 0:
                    pedaling_cad += e.cadence*interval
                    pedaling_cad_seconds += interval
                if e.power != None and e.power > 0:
                    pedaling_power += e.power*interval
                    pedaling_power_seconds += interval
                if e.temp != None:
                    temp += e.temp*interval
                    temp_seconds += interval
                    if e.temp > max_temp:
                        max_temp = e.temp
                    if e.temp < min_temp:
                        min_temp = e.temp
            if pedaling_cad and pedaling_cad_seconds:
                self.avg_pedaling_cad = int(round(float(pedaling_cad)/pedaling_cad_seconds))
            if pedaling_power and pedaling_power_seconds:
                self.avg_pedaling_power = int(round(float(pedaling_power)/pedaling_power_seconds))
            if temp and temp_seconds:
                self.avg_temp = round(float(temp)/temp_seconds)
                self.max_temp = max_temp
                self.min_temp = min_temp
                self.temperature = self.avg_temp

if __name__ == '__main__':
    import pprint
    import sys
    t = FITParser()
    t.parse_uploaded_file(file(sys.argv[1]))

    #if t.entries:
    #    print t.entries[0]
    #    print t.entries[-1]
    for e in t.entries:
        print e
    for lap in t.laps:
        print lap

    print 'start: %s %s - duration: %s - distance: %s' % (t.date, t.start_time, t.duration, t.distance_sum)
    print 'start - lat: %s - lon: %s' % (t.start_lat, t.start_lon)
    print 'end - lat: %s - lon: %s' % (t.end_lat, t.end_lon)
    print 'HR - avg: %s - max: %s' % (t.avg_hr, t.max_hr)
    print 'SPEED - avg: %s - max: %s' % (t.avg_speed, t.max_speed)
    print 'CADENCE - avg: %s - max: %s - pedal: %s' % (t.avg_cadence, t.max_cadence, t.avg_pedaling_cad)
    print 'POWER - avg: %s - max: %s - pedal: %s' % (t.avg_power, t.max_power, t.avg_pedaling_power)
    print 'TEMP - avg: %s - max: %s - min: %s' % (t.avg_temp, t.max_temp, t.min_temp)
    print 'LAPS: %s ENTRIES: %s' %(len(t.laps), len(t.entries))
