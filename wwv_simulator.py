from subprocess import Popen, PIPE
from enum import Flag, auto
from tempfile import TemporaryDirectory as tmpdir
from datetime import datetime, timedelta
from urllib.request import urlopen
from functools import reduce
from math import log
import shutil
import calendar
import time
import threading
import os
import argparse
import sys
import re

cache = {}
sox = "sox"
espeak_ng = "espeak"
rate = 44100
bits = 16
vol = 0.1
raw = f"-t raw -r{rate} -es -b{bits}"
second_bytes = rate * bits // 8
minute_bytes = second_bytes * 60

FINALS_CACHE = "9_FINALS.ALL_IAU2000_V2013_019.txt"
FINALS_URL = "https://datacenter.iers.org/data/latestVersion/9_FINALS.ALL_IAU2000_V2013_019.txt"
YCOMBINATOR_URL = "https://news.ycombinator.com/"
GEOALERT_URL = "https://services.swpc.noaa.gov/text/wwv.txt"

class Stations(Flag):
    WWV = auto()
    WWVH = auto()

class Tones(Flag):
    HOUR = auto()
    MINUTE = auto()
    BCD_LONG = auto()
    BCD_SHORT = auto()
    BCD_MARKER = auto()
    TICK = auto()
    TICK_SHORT = auto()
    DOUBLE_TICK = auto()
    EXTRA_TICK = auto()
    H440 = auto()
    H500 = auto()
    H600 = auto()

station_names = {
    "wwv": Stations.WWV,
    "wwvh": Stations.WWVH,
}

scripts = {
    Tones.HOUR : "synth 0.8 sine 1500 pad 0 0.2",
    Tones.MINUTE : "synth 0.8 sine 1200 pad 0 0.2",
    Tones.BCD_LONG : "synth 0.50 sine 100 pad 0 0.5",
    Tones.BCD_SHORT : "synth 0.20 sine 100 pad 0 0.8",
    Tones.BCD_MARKER : "synth 0.80 sine 100 pad 0 0.2",
    Tones.TICK : "synth 0.005 sine 1200 pad 0 0.995",
    Tones.TICK_SHORT : "synth 0.005 sine 1200 pad 0.01 0.025",
    Tones.DOUBLE_TICK : f"synth 0.005 sine 1200 pad 0 0.11 vol {vol} : synth 0.005 sine 1200 pad 0 0.88",
    Tones.EXTRA_TICK : "synth 0.005 sine 1200 pad 0.1 0.88",
    Tones.H440 : "synth 1 sine 440",
    Tones.H500 : "synth 1 sine 500",
    Tones.H600 : "synth 1 sine 600",
}

hertz = {
    Stations.WWV: {
        Tones.H500: { i for i in range(60)[4::2] }, # even
        Tones.H600: { i for i in range(60)[1::2] }, # odd
        Tones.H440: { 2 },
        None: { 0, 3, 4, 8, 10, 18, 29, 30, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 59 },
    },
    Stations.WWVH: {
        Tones.H500: { i for i in range(60)[3::2] }, # odd
        Tones.H600: { i for i in range(60)[::2] }, # even
        Tones.H440: { 1 },
        None: { 0, 3, 4, 8, 9, 10, 11, 14, 15, 16, 17, 18, 19, 29, 30, 45, 47, 48, 49, 50, 51, 52, 59 },
    }
}

announcements = {
    Stations.WWV: {
        0: "station_id",
        4: "io_exp_announce",
        8: "io_exp",
        10: "mars_announce",
        18: "geoalerts",
        30: "station_id",
    },
    Stations.WWVH: {
        3: "io_exp_announce",
        29: "station_id",
        45: "geoalerts",
        47: "availability",
        48: "io_exp",
        50: "mars_announce",
        52: "availability",
        59: "station_id",
    },
}

station_id_text = {
    Stations.WWV: "This is a simulation of Radio Station WWV, Fort Collins, Colorado, broadcasting on internationally allocated standard carrier frequencies of 2 point 5. 5. 10. 15 and 20 megahertz, providing time of day, standard time interval and other related information. ",
    Stations.WWVH: "This is a simulation of Radio Station WWVH, Kekaha, Hawaii, broadcasting on internationally allocated standard carrier frequencies of 2 point 5. 5. 10. 15 and 20 megahertz, providing time of day, standard time interval and other related information. ",
}
station_signoff_text = "Enquiries regarding this simulation may be directed to github dot com, slash kuremu, slash WWV, underscore simulator."

exp_notice_text = {
    Stations.WWV: "Beginning November 15th, 2021, NIST will be broadcasting a test signal on minute 8 of each hour on WWV, and minute 48 on WWVH. This signal has been created to assist in ionospheric research, and is a joint effort of the Ham Radio Citizen's Science Investigation and NIST. The signal consists of various tones, chirps and noise bursts. The signal will be broadcast for several weeks. For more information on Ham Sci and the WWV WWVH project go to www dot ham sci dot org slash wwv.",
    Stations.WWVH: "Beginning November 15th, 2021 WWV and WWVH will be broadcasting a test signal on minute 8 of each hour on WWV and minute 48 on WWVH. This signal has been created to assist in ionospheric research, and is a joint effort of NIST and the Ham Radio Citizen's Science Investigation, or Ham Sci. The signal consists of various tones, chirps and noise bursts, and may be modified occasionally. For more information on Ham Sci and the WWV and WWVH project go to H, A, M, S, C, I, dot org.",
}
exp_text = "What follows is a scientific modulation test. For more information, visit ham sci dot org slash WWV."
exp_high = "synth 0.97 sawtooth mix 1000 sinc 2k sinc -4k pad 0.03"
exp_high_seq = " : ".join([ f"{exp_high} vol {int(1000*(((10-i)/10)**2)*0.5)/1000}" for i in range(10)])
exp_synth = f"""
        synth 0.97 tpdfnoise vol 0.01 pad 10.03 :
        synth 0.97 tpdfnoise vol 0.005 pad 0.03 1 :
        {exp_high_seq} pad 0 1 :
        synth 0.06 sine mix 0:5k vol {vol} pad 0 0.09 repeat 2 :
            synth 0.06 sine mix 5k:0 vol {vol} pad 0 0.09 repeat 2 pad 0 0.5 :
        synth 1 sine mix 0:4.8k vol {vol} pad 0 0.1 repeat 2 :
            synth 1 sine mix 4.8k:0 vol {vol} pad 0 0.1 repeat 2 pad 0 2 :
        synth 0.002 whitenoise vol 0.04 pad 0 0.158 repeat 5 :
            synth 0.002 whitenoise vol 0.04 pad 0 0.158 sinc -13k repeat 5 pad 0 1.08 :
        synth 0.97 tpdfnoise vol 0.01 pad 0.03 :
            synth 0.97 tpdfnoise vol 0.005 pad 0.03 pad 0 1
"""

availability_text_wwvh = "Your attention, please. The WWVH audio signal is available by telephone. The audio signal heard on the WWVH radio broadcast is available by telephone, including all times, timecodes, audio frequency and announcement information heard on the broadcast. The audio signal is available at: area code 8 oh 8, 3 3 5, 4 3 6 3. To repeat, the WWVH audio signal is available at: 8 oh 8, 3 3 5, 4 3 6 3."

announcers = {
    Stations.WWV: "-ven+m1 -k10 -s153 --punct=\"<characters>\"",
    Stations.WWVH: "-ven+f2 -k5 -s152 --punct=\"<characters>\"",
}

def err(*msgs):
    sys.stderr.write(f"{', '.join(str(m) for m in msgs)}\n")
    sys.stderr.flush()

def run(cmd, *args, **kwargs):
    return Popen(cmd.split(' '), *args, **kwargs)

"""
Get text document.
"""
def curl(url, timeout=10):
    try:
        r = urlopen(url, timeout=10)
        message = r.read().decode("utf-8")
    except:
        message = None
    return message if message else ""

"""
Retrieve and cache file.
"""
def cache_file(url, file):
    if url in cache:
        return
    cache[url] = True
    try:
        r = urlopen(url, timeout=10)
        if r:
            with open(file, "wb") as f:
                f.write(r.read())
    except:
        r = None
    finally:
        del cache[url]

"""
Retrieve DUT1 and leap second.
"""
def get_dut1(date):
    if os.path.exists(FINALS_CACHE):
        # data file starts at 2/1/73
        start = datetime.strptime(f"2/1/73", "%d/%m/%y")
        start_month = date - timedelta(days=date.day - 1)
        month_days = calendar.monthrange(date.year, date.month)[1] + 1
        # length of one line in bytes
        llen = 188
        with open(FINALS_CACHE, "rb") as f:
            # seek to start of month
            f.seek(llen * (start_month - start).days)
            try:
                # get date/dut1 for each day of the month plus first day of next month
                days = [ (start_month + timedelta(days=i), float(line[58:68]), i == date.day - 1) \
                        for (i, line) in [(i, f.read(llen).decode("utf-8").strip()) \
                        for i in range(month_days) ]]
            except:
                # we are presumably out of range
                return (0, False)
        # update cache once every month
        if time.time() - os.path.getmtime(FINALS_CACHE) > 30 * 24 * 60 * 60:
            threading.Thread(target=cache_file, args=(FINALS_URL,FINALS_CACHE,), daemon=True).start()
        # dut1, rounded to nearest 0.1
        dut1 = round(days[date.day - 1][1] * 10) / 10
        # whether a leap second is to occur
        # (1st_day_of_next_month.dut1 - last_day_of_this_month.dut1 > 0.9
        # indicates a leap second has been added)
        leap_second = days[-1][1] - days[-2][1] > 0.9
        return (dut1, leap_second)
    else:
        # cache data file for the first time
        threading.Thread(target=cache_file, args=(FINALS_URL,FINALS_CACHE,), daemon=True).start()
    return (0, False)

def tz_is_dst(tz):
    return str(tz) in [ "ADT", "IDT", "IRDT", "ACDT", "AEDT", "AWDT", "LHDT", "CDT", "CIDST", "MSD", "ADT", "AKDT", "CDT", "EDT", "HADT", "MDT", "NDT", "PDT", "PMDT", "CHADT", "NZDT", "WAST", "WST", "AMST", "ANAST", "AZST", "IRKST", "KRAST", "MAGST", "NOVST", "OMSST", "PETST", "VLAST", "YAKST", "YEKST", "AZOST", "BST", "CEST", "EEST", "WEST", "EGST", "WGST", "EASST", "FJST", "AMST", "BRST", "CLST", "FKST", "PYST", "UYST", "WARST", "PT", "MT", "ET", "CT", "AT" ]

"""
Get daylight savings time in/out dates.
"""
def get_dst(now):
    utcoffset = now.astimezone().utcoffset()

    now_end = now.replace(hour=23, minute=59, second=59)
    now_end_local = now_end + utcoffset

    prev_end = now_end - timedelta(hours=24)
    prev_end_local = prev_end + utcoffset

    return (tz_is_dst(now_end_local.astimezone().tzinfo), tz_is_dst(prev_end_local.astimezone().tzinfo))

"""
Generate speech.
"""
def speak(message, announcer, delay=0, duration=0):
    speak_proc = Popen([espeak_ng, "--stdout"] + announcer.split() + [message], stdout=PIPE)
    sox_proc = run(f"{sox} -V1 -t wav - {raw} - delay {delay} vol {vol} trim 0 {duration}", stdin=speak_proc.stdout, stdout=PIPE)
    return sox_proc.stdout.read();

"""
Retrieve hertz from appropriate table.
"""
def get_hertz(station, minute):
    table = hertz[station]
    if minute not in table[None]:
        for (h, minutes) in table.items():
            if minute in minutes:
                return h
    return None

"""
Merge audio data.
"""
def merge_audio(*audios):
    with tmpdir() as tmp:
        files = []
        for (i, a) in enumerate(audios):
            file = os.path.join(tmp, f"audio{i}")
            with open(file, 'wb') as f:
                f.write(a)
            files.append(file)
        merge_str = " ".join([ f"{raw} {file}" for file in files])
        gain_arg = "gain %s" % (20 * log(len(audios)) / log(10))
        merged = run(f"{sox} -m {merge_str} {raw} - {gain_arg}", stdout=PIPE)
        return merged.stdout.read()

"""
Merge and cache tones.
"""
def merge_tones(tones):
    # OR tone enums for cache
    key = tones[0]
    [key := key | k for k in tones[1:]]
    if key in cache:
        return cache.get(key)
    selected = [ scripts[t] for t in tones ]
    with tmpdir() as tmp:
        files = []
        for (i, script) in enumerate(selected):
            path = os.path.join(tmp, f"script{i}")
            with open(path, 'w') as f:
                proc = run(f"{sox} -n {raw} - {script} vol {vol}", stdout=f).wait()
            files.append(path)
        # raw formatted file inputs
        merge_str = " ".join([ f"{raw} {file}" for file in files])
        # -m only if we are actually combining
        mix_arg = "-m " if len(tones) > 1 else ""
        # gain to make up for automatically reduced volume during merge
        gain_arg = "gain %s" % (20 * log(len(tones)) / log(10))
        merged = run(f"{sox} {mix_arg}{merge_str} {raw} - {gain_arg}", stdout=PIPE)
        cache[key] = merged.stdout.read()
    return cache.get(key)

"""
Ionospheric experiment announcement.
"""
def io_exp_announce(station, now):
    return speak(exp_notice_text[station], announcers[station], 1, 44)

"""
Ionospheric experiment.
"""
def io_exp(station, now):
    synth_str = ' '.join((s.strip() for s in exp_synth.splitlines())).strip()
    sox_cmd = f"{sox} -n {raw} - {synth_str}"
    io_out = run(sox_cmd, stdout=PIPE).stdout.read()
    speech_out = speak(exp_text, announcers[station], 1, 44)
    return merge_audio(io_out, speech_out)

"""
MARS announcements (HackerNews top posts).
"""
def mars_announce(station, now):
    message = curl(YCOMBINATOR_URL)
    lines = "".join(message.splitlines())
    st = re.findall(r'class="titlelink">(.*?)</a>', lines)
    return speak(f"Top posts from news dot why combinator dot com. {'. '.join(st[:7])}", announcers[station], 1, 44)

"""
WWVH broadcast availability announcement.
"""
def availability(station, now):
    return speak(availability_text_wwvh, announcers[station], 1, 44)

"""
Station ID.
"""
def station_id(station, now):
    message = station_id_text[station] + station_signoff_text
    if station == Stations.WWVH:
        message += " Aloha."
    return speak(message, announcers[station], 1, 44)

"""
Geophysical alerts.
"""
def geoalerts(station, now):
    message = curl(GEOALERT_URL)
    message = " ".join(message.splitlines()[6:])
    return speak(message, announcers[station], 1, 44)

"""
Time announcement.
"""
def time_announce(station, next, delay):
    message = f"At the tone, {next.hour} hours, {next.minute} minutes, Coordinated Universal Time"
    return speak(message, announcers[station], delay, 15)

"""
Binary coded decimal time code.
"""
def bcd_frame(now, dut1, leap_second):
    # binary list BCD_LONG/BCD_SHORT padded to s derived from single decimal char
    pulse = lambda val, s: [Tones.BCD_LONG if i == '1' else Tones.BCD_SHORT for i in bin(int(val))[2:]][::-1] + [ Tones.BCD_SHORT ] * (s - len(bin(int(val))[2:]))
    # zfill a value
    z = lambda val, n: str(val).zfill(n)
    # day of year
    day = now.timetuple().tm_yday

    # dut1 no more than 0.7
    dut1_abs = int(abs(dut1) * 10)
    if dut1_abs > 7:
        dut1_abs = 7

    # dst flag appears/disappears at 00:00 UTC on the day of local switchover
    # second dst flag the same but delayed by a day
    dst = get_dst(now)

    # begin BCD frame
    frame = [ Tones.BCD_SHORT ] * 60 # initialise with 0
    frame[1] = Tones.BCD_SHORT # always short
    frame[2] = Tones.BCD_LONG if dst[1] else Tones.BCD_SHORT # 2 DST INDICATOR #2
    frame[3] = Tones.BCD_LONG if leap_second else Tones.BCD_SHORT # 3 LEAP SECOND WARNING
    frame[4:8] = pulse(z(now.year, 2)[-1], 4) # 4-7 YEAR UNITS
    frame[9] = Tones.BCD_MARKER # 9 MARKER
    frame[10:14] = pulse(z(now.minute, 2)[-1], 4) # 10-13 MINUTES UNITS
    frame[15:18] = pulse(z(now.minute, 2)[-2], 3) # 15-17 MINUTES TENS
    frame[19] = Tones.BCD_MARKER # 19 MARKER
    frame[20:24] = pulse(z(now.hour, 2)[-1], 4) # 20-23 HOURS UNITS
    frame[25:27] = pulse(z(now.hour, 2)[-2], 2) # 25-26 HOURS TENS
    frame[29] = Tones.BCD_MARKER # 29 MARKER
    frame[30:34] = pulse(z(day, 3)[-1], 4) # 30-33 DAYS UNITS
    frame[35:39] = pulse(z(day, 3)[-2], 4) # 35-38 DAYS TENS
    frame[39] = Tones.BCD_MARKER # 39 MARKER
    frame[40:42] = pulse(z(day, 3)[-3], 2) # 40-41 DAYS HUNDREDS
    frame[49] = Tones.BCD_MARKER # 49 MARKER
    frame[50] = Tones.BCD_SHORT if dut1 < 0 else Tones.BCD_LONG # 50 UT1 CORRECTION SIGN
    frame[51:55] = pulse(z(now.year, 2)[-2], 4) # 51-54 YEAR TENS
    frame[55] = Tones.BCD_LONG if dst[0] else Tones.BCD_SHORT # 55 DST INDICATOR #1
    frame[56:59] = pulse(dut1_abs, 3) # 56-58 UT1 CORRECTION
    frame[59] = Tones.BCD_MARKER # 59 MARKER
    
    # first pulse omitted
    return frame[1:]

"""
Generate a minute of audio.
"""
def gen_minute(minute, station, dut1, leap_second):
    #err(f"Generating {station} {minute}")
    bcd_next = lambda: bcd.pop(0)
    normal_tick = lambda: merge_tones([bcd_next()] + freq)
    extra_tick = lambda: merge_tones([Tones.EXTRA_TICK, bcd_next()] + freq)
    no_freq_tick = lambda: merge_tones([bcd_next()])
    repeat = lambda d, n: reduce(lambda a,b: a+b, (d() for _ in range(n)), b"")

    # bcd frame
    bcd = bcd_frame(minute, dut1, leap_second)

    # standard frequency
    freq = get_hertz(station, minute.minute)
    # 440 tone omitted during first hour of each day
    if freq is None or \
            (station == Stations.WWV and minute.hour == 0 and minute.minute == 2) or \
            (station == Stations.WWVH and minute.hour == 0 and minute.minute == 1):
        freq = []
    else:
        freq = [freq]

    # hour or minute tone
    first = Tones.HOUR if minute.minute == 0 else Tones.MINUTE
    data = merge_tones([first])

    # first 16 ticks after minute encode DUT1 correction
    # each double tick is 1ms of difference between UTC and UT1
    # if the double ticks occur in the first 8 seconds the difference is positive, else negative
    dut1_ticks = repeat(normal_tick, 8) if dut1 <= 0 else b""
    dut1_ticks += repeat(extra_tick, int(abs(dut1 / 1) * 10)) + repeat(normal_tick, int(8 - abs(dut1 / 1) * 10))
    dut1_ticks += repeat(normal_tick, 8) if dut1 > 0 else b""

    # potential announcement during 1-45 seconds
    announce = dut1_ticks
    announce += repeat(normal_tick, 12) # 16-28 normal
    announce += merge_tones([bcd_next()] + freq) # 29 second silenced
    announce += repeat(normal_tick, 15) # 30-44 normal
    # check for announcement
    announcement = announcements[station].get(minute.minute)
    if announcement:
        announce = merge_audio(announce, eval(announcement)(station, minute))
    data += announce

    # time announcement in last 15 seconds
    time = repeat(no_freq_tick, 14) # 45-59 standard freq silenced
    next = minute + timedelta(minutes=1)
    data += merge_audio(time, time_announce(station, next, 1 if station == Stations.WWVH else 7.5)) # merge announcement
    data += merge_tones([bcd_next()]) # 59 second silenced, standard freq silenced

    # to force silence at tick during announcements etc. render them separately
    # and copy directly to the bytearray
    short_tick = merge_tones([Tones.TICK_SHORT])
    l = len(short_tick)
    data = list(data)
    ms10 = 0.01 * second_bytes
    for i in [i for i in range(60) if i not in [0, 29, 59]]:
        j = int(i * second_bytes - ms10) # 0.01 silence before tick
        data[j:j+l] = short_tick
    data = bytes(data)

    # just add another short BCD tone for leap second
    if leap_second and minute.hour == 23 and minute.minute == 59:
        data += merge_tones([Tones.BCD_SHORT])

    return data

"""
Get number of samples into the current minute.
"""
def sample_offset(start, now=None):
    # microseconds into the minute when we generated audio_data
    microseconds = start.second * 1e6 + start.microsecond
    # any delay between generation and now
    delay = (now - start) / timedelta(microseconds=1) if now else 0
    # ratio of whole minute to offset
    expired = (microseconds + delay) / 120e6
    # get offset for 1 minute of audio data
    offset = int(minute_bytes * 2 * expired)
    # even to prevent audio glitch (16-bit)
    if offset % 2 != 0:
        offset -= 1
    # return trimmed data
    return offset

"""
Update audio data object.
"""
def update_data(data, time):
    (dut1, leap_second) = get_dut1(time)
    audio = gen_minute(time, station, dut1, leap_second)
    data.swap_inactive(audio)

"""
Print date/time to stderr.
"""
def run_clock(offset):
    while True:
        sys.stderr.write("\x1b[1K\r")
        sys.stderr.write((datetime.utcnow() + offset).strftime("%d/%m/%Y, %H:%M:%S"))
        sys.stderr.flush()
        time.sleep(1 - datetime.utcnow().microsecond / 1e6)

"""
Double buffer for audio data.
"""
class AudioData(object):
    def __init__(self, a=b"", b=b""):
        self.i = 0
        self.a = a
        self.b = b

    def read(self):
        size = second_bytes - self.i % second_bytes
        start = self.i % len(self.a)
        end = start + size
        buffer = self.a[start:end]
        self.seek(len(self.a) if end >= len(self.a) else self.i + size)
        return buffer

    def swap_inactive(self, audio):
        self.b = audio

    def a_active(self):
        return self.i < len(self.a)

    def seek(self, i):
        self.i = i % len(self.a)
        if self.i < i:
            self.a, self.b = self.b, self.a

for c in [sox, espeak_ng]:
    if shutil.which(c) is None:
        sys.stderr.write(f"{c} not found\n")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Simulate WWV/WWVH time signal')
    names = [s for s in station_names.keys()]
    parser.add_argument("--station", dest="station", choices=names, nargs='?', default=names[0], help="station (WWV/WWVH)")
    parser.add_argument("--date", dest="date_str", nargs='?', help="custom date d/m/y")
    parser.add_argument("--time", dest="time_str", nargs='?', help="custom time H:M:S")
    parser.add_argument("--period", dest="period", nargs='?', help="output given duration of audio and exit H:M:S")
    parser.add_argument("--clock", action="store_true", help="output broadcast time to stderr")
    parser.add_argument(dest="output", default="-d", nargs='?', help="output destination appended to sox. a value of '-' writes 44.1k 16-bit signed-integer samples to stdout.")

    args = parser.parse_args()
    station = station_names[args.station]
    output = args.output or "-d"

    if output == '-':
        out = sys.stdout.buffer
    else:
        proc = run(f"{sox} -q {raw} - {output}", stdin=PIPE)
        out = proc.stdin

    start = datetime.utcnow()

    # offset if custom date/time set
    if args.date_str or args.time_str:
        date_str = args.date_str or start.strftime("%d/%m/%y")
        time_str = args.time_str or start.strftime("%H:%M:%S")
        dt = datetime.strptime(f"{date_str} {time_str}", "%d/%m/%y %H:%M:%S")
        offset = (dt - start)
    else:
        offset = None

    # announced minute
    current_minute = start + offset if offset else start
    # update at roughly half minute
    next_update = start + timedelta(minutes=1, seconds=30 - current_minute.second, microseconds=-current_minute.microsecond)

    # if period set, output all audio at once
    if args.period:
        current_minute = start + offset if offset else start
        p = datetime.strptime(f"{args.period}", "%H:%M:%S")
        seconds = timedelta(hours=p.hour, minutes=p.minute, seconds=p.second).total_seconds()
        audio_bytes = int(seconds * second_bytes)
        (dut1, leap_second) = get_dut1(current_minute)
        audio = gen_minute(current_minute, station, dut1, leap_second)
        current_minute += timedelta(minutes=1)
        samples = sample_offset(dt) if offset else sample_offset(start)
        audio = audio[samples:] # offset into minute
        while len(audio) < audio_bytes:
            (dut1, leap_second) = get_dut1(current_minute)
            audio += gen_minute(current_minute, station, dut1, leap_second)
            current_minute += timedelta(minutes=1)
        audio = audio[:audio_bytes] # trim final result
        out.write(audio)
        sys.exit()

    # clock thread
    if args.clock:
        clock_delay = (datetime.utcnow() - start) / timedelta(microseconds=1) if not offset else 0
        clock_offset = offset if offset else timedelta()
        threading.Thread(target=run_clock, args=(clock_offset + timedelta(microseconds=clock_delay),), daemon=True).start()

    # generate initial audio
    (dut1, leap_second) = get_dut1(current_minute)
    a = gen_minute(current_minute, station, dut1, leap_second)
    current_minute += timedelta(minutes=1)
    (dut1, leap_second) = get_dut1(current_minute)
    b = gen_minute(current_minute, station, dut1, leap_second)
    data = AudioData(a, b)

    # seek to initial offset of first minute
    samples = sample_offset(dt) if offset else sample_offset(start, datetime.utcnow())
    data.seek(samples)

    # write a few seconds to start
    out.write(data.read() + data.read() + data.read() + data.read() + data.read() + data.read())

    while True:
        out.write(data.read())
        # update every half minute
        if (next_update - datetime.utcnow()).total_seconds() < 0:
            next_update += timedelta(minutes=1)
            current_minute += timedelta(minutes=1)
            threading.Thread(target=update_data, args=(data,current_minute,), daemon=True).start()
        # sleep until next tick
        time.sleep(1 - time.monotonic() % 1)
